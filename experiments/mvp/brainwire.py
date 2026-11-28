"""PROTOTYPE ONLY - mvp36 (DESIGN.md section 35): the chat core (brain/) behind a switch in the bot, first slice.

Today's bot (handler.py) stays as it is. For a person `config.brain_on` names, the chat core is tried for a message
that today's own reading says is a question and not a request to do something, at two sites of answer_normally:
- H1, inside `history.history_reads` (before the cap check): a message today's history parse takes (`read_recall`
  or `read`), unless today's own history answer owns the screen and its follow-up read takes the message;
- H2, after the interpreter and its guards, before `history.after_interpret`: an interpretation with no `also` whose
  intent is a talking one (ASK_INTENTS), or `follow_up` while the chat core's own answer owns the screen.
Its answer is sent only when code can see it is a history answer (`decide`). Every other case returns None and
today's bot goes on with the same message (and, at H2, the same interpretation), as with the switch off.

This module is imported only inside the switched branch: with the switch off nothing of brain/ is imported.

The measured configuration is pinned here and passed explicitly to brain/ (its import-time defaults, read from the
environment, are not the measured ones and are not changed): the prompt file, the values check with its default
rules, strict off on every tool, the model, effort, thinking, max_tokens, streaming, rounds and deadlines.

Privacy: the turn record (their message, the model's blocks, the tool results) stays in memory; nothing of it is
written to disk here. `runs.steps` holds shapes only. The carried private topic lives only in this module's one state
key (`brain:<handle>`, cleared by "delete my data"), never on the screen the model reads, in a run row or the trace.
"""
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config, llm
from .brain import answer as A
from .brain import loop as BL
from .brain import provider as P
from .brain import tools as TL
from .brain import verify as V

# ---------------------------------------------------------------- the measured configuration, pinned
PROMPT_VERSION = "brain_v4d"
PROMPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", f"{PROMPT_VERSION}.md")
MODEL = "claude-haiku-5-5"
EFFORT = "low"
THINKING = "adaptive"
MAX_TOKENS = 4000
STREAM = True
STRICT = False                      # strict off on every tool (the run's MVP_BRAIN_STRICT=0)
LOOSE = ("give_answer",)            # as the run's --loose give_answer (the settings it records)
ROUNDS, SOFT_S, DEEP_S, HARD_S = 3, 7.0, 11.0, 15.0
NUMBER_WORDS = "refuse"
# the values check with its default rules (the environment's MVP_BRAIN_VALUES_RULES is not read here)
CHECK_RULES = V.VALUES_RULES | V.VALUES_RULES_R30 | V.VALUES_RULES_R31 | V.VALUES_RULES_R32
CHECK = V.values_mode(number_words=NUMBER_WORDS, rules=CHECK_RULES)
PURPOSE = "brain"                   # the ledger's purpose for the bot's own requests (the eval's is "brain_eval")

# ---------------------------------------------------------------- the sites and the screen
STATE = "brain:{h}"                 # ends in ":<handle>": "delete my data" clears it
FRESH_HOURS = 6
GOAL = "history: brain"
# H2: the intents tried always (nothing is pending, by eligibility, so a "confirm" confirms nothing), and those tried
# only while the chat core's own answer owns the screen (a follow-up belongs to whoever answered last)
ASK_INTENTS = ("ask", "chat", "library_stats", "clarify", "unsupported", "confirm")
# (A2-02) `feedback` is never tried: today's `_feedback` writes on every one (the rows, `lastwrite`, the level), and
# a write is never lost
OWN_INTENTS = ("follow_up",)
STOP_TOOLS = ("search", "learned")  # their backends are unset in this slice: a turn that calls one is declined
STOPPED = "stopped_at_search"       # the provider error the proxy raises (code's words)

# ---------------------------------------------------------------- claimed actions (the send decision, not verify.py)
# today's verify.OUTCOME, plus the future and promise forms it misses. Read per sentence, apostrophes made plain,
# with quoted spans and every name the turn's results show taken out first (a title quoted as data is no claim).
# repair of mvp36 (finding F03): up to two adverbs between the subject and the verb ("I've also set up", "I will
# definitely send"), "we" beside "I", more verbs (create, text, put ... on, let you know, remember, make sure, turn ...
# on), the progressive ("I'll be emailing", "I'm sending"), the offer ("I can send you"), and the short forms with no
# subject, anchored to the whole sentence or to "your <list or inbox>" so a true "Saved ..." about their saves passes.
# second repair (fix2, A2-04, A2-06): contractions made plain first ("it's been" -> "it has been", "they're" -> "they
# are", "I`ve" / "I'v" / "Ive" -> "I've"); up to five adverbs; "you'll now get"; "have it sent" (the causative); the
# passive with a place or "to you" ("was added to your list", "was emailed to you"; never "sent to you by a friend");
# "noted", "on it", "<doing> now" with no subject; queued, lined up, arranged, set a reminder, follow up, check back,
# get it over to you, write it down; "goes out every ...", "on its way", "is now on", "your list now has"; the offer
# of a thing the chat core cannot do, as a question or not ("want me to email ...", "should I add ...", "I could
# add ..."). And a few true forms the first forms caught: "start from May", "keep to YouTube", "remember only",
# "add Shorts" (A2-08). Every form reads the sentence both as written and with its contractions made plain, so a form
# that names a contraction ("it's sent", verify.OUTCOME) still sees it.
_ADV = (r"(?:(?:also|just|now|already|then|actually|definitely|certainly|really|quickly|automatically|successfully|"
        r"gladly|happily|soon|shortly|regularly|right away|go ahead and|gone ahead and|went ahead and)\s+){0,5}")
_OBJ = r"(?:it|that|this|them|these|those|one|you|everything)"
_WILL = r"\b(?:i|we)(?:'ll| will| shall|'m going to| am going to|'re going to| are going to|'m gonna| can)\s+"
_MONTH = (r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*|\d{4}|the (?:start|beginning|end)|"
          r"(?:last|this) (?:year|month|week)")
_DO = (r"(?:send|e-?mail|remind|schedule|set (?:" + _OBJ + r" )?up|set (?:a|an|the|your) (?:reminder|alarm|timer|"
       r"rule|alert)|save|add(?! (?:the )?shorts\b)|turn (?:" + _OBJ + r" )?on|"
       r"start(?! with\b| by\b| off\b| (?:from|in|at) (?:" + _MONTH + r")\b)|"
       r"keep(?! (?:this|it) (?:short|brief|simple)\b| to\b)|create|text|ping|notify|"
       r"message|forward|book|deliver|subscribe|sign you up|remember(?! only\b)|let you know|make sure|"
       r"put " + _OBJ + r" (?:on|in|into) your\b|queue|line (?:" + _OBJ + r" )?up|arrange (?:a|an|for)\b|"
       r"shoot you|get " + _OBJ + r" (?:over )?to you|follow up|check back|circle back|"
       r"(?:write|jot) " + _OBJ + r" down|make (?:you )?a (?:list|note|reminder)|"
       r"watch (?:out )?for (?:new|more)|have " + _OBJ + r" (?:all )?(?:sent|e-?mailed|added|saved|scheduled|set up|"
       r"forwarded|delivered|put))")
_DOING = (r"(?:sending|e-?mailing|reminding|scheduling|setting (?:" + _OBJ + r" )?up|saving|adding|creating|texting|"
          r"pinging|notifying|messaging|forwarding|booking|delivering|tracking|keeping (?:track|an eye)|queu(?:e)?ing)")
_DONE = (r"(?:sent|set (?:" + _OBJ + r" )?(?:all )?up|scheduled|saved|created|added|e-?mailed|booked|deleted|texted|"
         r"messaged|forwarded|delivered|subscribed|signed you up|turned (?:" + _OBJ + r" )?(?:on|off)|made a note|"
         r"made sure|put " + _OBJ + r" (?:on|in|into) your\b|queued|lined (?:" + _OBJ + r" )?up (?:a|an|for)\b|"
         r"arranged (?:a|an|for)\b)")
_PLACE = r"(?:to-?do|list|calendar|inbox|reminders|email|notes)\b"
_THING = r"(?:e-?mails?|reminders?|alarms?|rules?|alert[s]?|digests?|recaps?)"
_ASKED = r"(?:want me to|would you like me to|do you want me to|shall i|should i|can i|could i|may i)\s+"
CLAIMS = (
    V.OUTCOME,
    re.compile(_WILL + _ADV + r"(?:be\s+" + _DOING + r"|" + _DO + r")\b", re.I),
    re.compile(r"\b(?:i|we)(?:'ve| have|'d| had)?\s+" + _ADV + _DONE + r"(?!\w)", re.I),
    re.compile(r"\b(?:i'm|i am|we're|we are)\s+" + _ADV + _DOING + r"\b", re.I),
    re.compile(r"\bfrom now on\b", re.I),
    re.compile(r"\b(?:will|has|have) been (?:sent|e-?mailed|scheduled|set up|created|booked)\b", re.I),
    re.compile(r"\b(?:has|have) been (?:added|saved|put|forwarded|turned on)(?:\W*$| (?:to|into|on|in) your "
               + _PLACE + r"| for you\b)", re.I),
    re.compile(r"\bwill be (?:sent|e-?mailed|scheduled)\b", re.I),
    re.compile(r"\byou(?:'ll| will) " + _ADV + r"(?:be )?(?:get|getting|receive|receiving)\b", re.I),
    re.compile(r"\bi(?:'ve| have) " + _ADV + r"(?:noted|remembered)\b", re.I),
    re.compile(_WILL + _ADV + r"(?:note|jot down) " + _OBJ + r"\W*$", re.I),   # a bare "I'll note that." (A2-04)
    # the passive: a place of theirs, or "to you" with no sender ("sent to you by a friend" is history)
    re.compile(r"\b(?:was|were|got|is|are|has been|have been) " + _ADV + r"(?:all )?(?:sent|added|e-?mailed|created|"
               r"scheduled|saved|put|forwarded|delivered) (?:to|into|in|on) your " + _PLACE, re.I),
    re.compile(r"\b(?:was|were|got|has been|have been) " + _ADV + r"(?:e-?mailed|forwarded|delivered) to you\b"
               r"(?! by\b)", re.I),
    re.compile(r"\b(?:it|that|this|they|these|those|everything|the (?:list|e-?mail|reminder|rule|alert|digest|recap))"
               r" (?:got|was|were) " + _ADV + r"(?:sent|e-?mailed|scheduled|created|added|saved|set up|booked)\W*$",
               re.I),
    # the short forms with no subject
    re.compile(r"^\W*(?:sent|done|all set|scheduled|saved|added|booked|e-?mailed|reminder set|noted|on it|"
               r"queued)\W*$", re.I),
    re.compile(r"^\W*noted\b", re.I),
    re.compile(r"^\W*" + _DOING + r"\b.*\b(?:now|for you|to your|right away)\b", re.I),
    re.compile(r"^\W*(?:added|sent|e-?mailed|forwarded|saved|put) (?:" + _OBJ + r" )?(?:to|into|in|on) your "
               + _PLACE, re.I),
    re.compile(r"^\W*(?:scheduled|set|booked|queued) for\b", re.I),
    re.compile(r"^\W*(?:turned|switched) (?:on|off)\b", re.I),
    re.compile(r"\b(?:reminder|alarm|rule|alert|e-?mail|digest|recap)s? (?:(?:is|are|has been|have been) (?:now )?"
               r"(?:set|created|added|scheduled|on|live|active)|set|created|scheduled)\b", re.I),
    re.compile(r"\b" + _THING + r"\W+(?:on|set|scheduled)\W*$", re.I),
    re.compile(r"\b" + _THING + r" (?:are |is )?(?:now )?(?:turned|switched) (?:on|off)\b", re.I),
    re.compile(r"\byour (?:weekly |daily |monthly )?(?:digest|recap|reminder|rule|alert|email)s? (?:starts|will "
               r"start|begins|will begin|is on|is set|is scheduled|is ready|goes out|will go out)\b", re.I),
    re.compile(r"\b(?:will|'ll) go out\b|\bgoes out (?:every|each|on|weekly|daily|monthly)\b|\bon (?:its|their) way\b",
               re.I),
    re.compile(r"\b(?:you are|you're) all set\b", re.I),
    re.compile(r"\b(?:are|is) now (?:on|in) your " + _PLACE + r"|\byour (?:to-?do )?(?:list|calendar|inbox|reminders|"
               r"notes) now (?:has|holds|includes|contains|shows)\b", re.I),
    re.compile(r"\bexpect (?:it|them|this|these|one)\b|\bin your inbox\b", re.I),
    # the offer of a thing the chat core cannot do (A2-06): nothing could follow a "yes"
    re.compile(r"\b" + _ASKED + _ADV + r"(?:" + _DO + r")\b", re.I),
    re.compile(r"\b(?:i|we) could\s+" + _ADV + r"(?:" + _DO + r")\b", re.I),
)
# contractions made plain before the forms are read (fix2, A2-04)
_PLAIN = ((re.compile(r"\b(it|that|this|there|everything|what|which|who)'s been\b"), r"\1 has been"),
          (re.compile(r"\b(they|we|you)'ve been\b"), r"\1 have been"),
          (re.compile(r"\b(they|we|you)'re\b"), r"\1 are"),
          (re.compile(r"\b(it|that|this|there)'s\b"), r"\1 is"),
          (re.compile(r"\bi'v(?=\s)"), "i've"), (re.compile(r"\bive\b"), "i've"))
_QUOTED = re.compile(r"\"[^\"]{1,200}\"|“[^”]{1,200}”")


def system_text():
    with open(PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


def tool_list():
    return BL.tool_list()


def new_provider():
    """The provider with the measured settings, every one passed explicitly."""
    return P.AnthropicProvider(model=MODEL, effort=EFFORT, max_tokens=MAX_TOKENS, prompt_version=PROMPT_VERSION,
                               purpose=PURPOSE, thinking=THINKING, strict=STRICT, loose=LOOSE, cache=True,
                               stream=STREAM)


_PROV = {"p": None}
_PROV_LOCK = threading.Lock()


def provider(bot):
    """`bot.brain_provider` when set (the tests' fakes), else one provider for the process (it is thread-safe),
    its connections opened in the background on first use (free count_tokens requests, nothing billed or logged)."""
    p = getattr(bot, "brain_provider", None)
    if p is not None:
        return p
    with _PROV_LOCK:
        if _PROV["p"] is None:
            _PROV["p"] = new_provider()
            threading.Thread(target=_warm, args=(_PROV["p"],), daemon=True, name="brain-warm").start()
        return _PROV["p"]


def _warm(p):
    try:
        p.warm(system_text(), tool_list(), connections=1)
    except Exception:  # noqa: BLE001 - warming is a convenience; the first request opens its own connection
        pass


class StopAtSearch:
    """A thin proxy over the provider, owned by the wiring: once a call to `search` or `learned` is in the messages
    (the turn will be declined), the next request is not sent and the turn ends as on a provider failure. Every other
    request passes through unchanged, so a turn that calls neither gives the same record. Attributes are the
    provider's own (the loop holds calls to the schema when the provider says it has a `strict`)."""

    def __init__(self, inner):
        self._inner = inner
        self.stopped_at = None

    def __getattr__(self, k):
        if k == "_inner":
            raise AttributeError(k)
        return getattr(self._inner, k)

    def send(self, system, tools, messages, max_tokens=None, timeout=None):
        if asked_stop_tool(messages):
            self.stopped_at = time.monotonic()
            raise P.ProviderError(STOPPED)
        return self._inner.send(system, tools, messages, max_tokens=max_tokens, timeout=timeout)


def _field(b, k):
    return b.get(k) if isinstance(b, dict) else getattr(b, k, None)


def asked_stop_tool(messages):
    for m in messages or ():
        if not isinstance(m, dict) or m.get("role") != "assistant" or not isinstance(m.get("content"), list):
            continue
        if any(_field(b, "type") == "tool_use" and _field(b, "name") in STOP_TOOLS for b in m["content"]):
            return True
    return False


# ---------------------------------------------------------------- the state: who owns the screen
def now_words(now, tz):
    """The screen's "now", in code's words and the eval's format: "Sun 22 Nov 2026 12:00, America/New_York"."""
    t = now.astimezone(ZoneInfo(tz))
    return f"{t:%a} {t.day} {t:%b %Y %H:%M}, {tz}"


def fresh_state(bot, h, now):
    """The chat core's own state while its answer is the one on screen: within FRESH_HOURS and its run id the last
    answer's. Else None (a stale one starts a new screen)."""
    st = bot.store.get_state(STATE.format(h=h))
    if not isinstance(st, dict):
        return None
    try:
        at = datetime.fromisoformat(st["at"])
        if now - at > timedelta(hours=FRESH_HOURS):   # (F09) a time with no zone raises TypeError here: not fresh
            return None
    except (KeyError, TypeError, ValueError):
        return None
    if (bot.store.last_answer(h) or {}).get("run_id") != st.get("run_id"):
        return None
    return st


def owns_screen(bot, h, now):
    return fresh_state(bot, h, now) is not None


def screen_for(st, now, tz):
    """The screen for this message: code's "now" and, after a fresh answer of the chat core, that answer's screen
    (loop.screen_after) with the real minutes since it."""
    scr = {"now": now_words(now, tz)}
    if st and isinstance(st.get("screen"), dict):
        scr = dict(st["screen"])
        la = dict(scr.get("last_answer") or {})
        try:
            gap = max(0.0, (now - datetime.fromisoformat(st["at"])).total_seconds())
        except (KeyError, TypeError, ValueError):
            gap = 0.0
        la["minutes_ago"] = int(gap // 60)
        scr["last_answer"] = la
        scr["now"] = now_words(now, tz)
    return scr


def window_of(st):
    d = (st or {}).get("window")
    if not isinstance(d, dict):
        return None
    from . import history as Hm
    try:
        return Hm.Window.model_validate(d)
    except Exception:  # noqa: BLE001 - a window that does not rebuild is not carried
        return None


# ---------------------------------------------------------------- eligibility
def _setup_open(bot, h):
    st = bot.store.get_state(f"onboard:{h}")
    return isinstance(st, dict) and st.get("step") not in (None, "done")


def not_eligible(bot, person, now):
    """Why the chat core is not tried for this message (code's words), or None."""
    h = person["handle"]
    if not config.brain_on(h):
        return "switch"
    if getattr(bot._tl, "brain_tried", False):
        return "tried"
    if "+anthropic" not in str(person.get("consent_version") or ""):
        return "consent"
    tl = bot._tl
    if any(getattr(tl, k, None) for k in ("in_split", "merged_text", "setup_text", "code_only")):
        return "open"
    if bot._live_pending(h, now) is not None or bot.open_draft(h, now) is not None or _setup_open(bot, h):
        return "open"
    if bot._over_cap(person):
        return "cap"
    if llm.spent_claude() + config.TOTAL_CAP_MARGIN_USD >= config.CLAUDE_CAP_USD:
        return "claude_cap"
    if getattr(bot, "brain_provider", None) is None and not (os.environ.get("DIGESTER_ANTHROPIC_API_KEY") or
                                                             os.environ.get("ANTHROPIC_API_KEY")):
        return "no_key"
    return None


# ---------------------------------------------------------------- the two sites
def at_h1(bot, person, text, now):
    """H1 (history.history_reads, after today's own follow-up read): today's parse took the message."""
    return try_turn(bot, person, text, now, "H1")


PLAIN_SOURCES = ("library", "recent")   # (fix2, X1) "recent": what they kept lately, read as a history question too


def plain_ask(spec):
    """(F01, F05) True when an `ask` is a question and nothing more: its only action the reply, now, no place, a read
    of the library (`library`, or `recent` since fix2: today's dispatch of such an ask writes only its own answer) and
    nothing from outside it. Anything else (a to-do, an email, new finds from YouTube; the sources todos, note, items,
    trends, recap) is today's."""
    if spec is None:
        return False
    return ([a.action for a in spec.do] == ["message.send"] and spec.when.type == "now" and spec.place is None
            and spec.content.source in PLAIN_SOURCES and spec.content.outside == "none")


def profile_write(bot, person, it, text):
    """(F02) True when today's _dispatch would merge a lasting fact into the profile for this message: a
    `profile_note` on the interpretation, or a level the text states that the profile does not already say (the same
    reading as _dispatch). Such a message is today's, so the write is never lost."""
    from . import profile as PR   # (handler.py calls this module P; here P is brain.provider)
    if getattr(it, "profile_note", None):
        return True
    said = PR.level_stated(text)
    if not said:
        return False
    return not PR.restates(PR.get(bot.store, person["handle"]), PR.level_phrase(said[1], said[2]))


# (fix2, X4) a message made only of courtesy words ("thanks!", "lol ok", "hi there") is never tried at H2, whatever its
# intent: the chat core would answer it with a history overview nobody asked for. Anchored to the WHOLE message, so it
# never matches a message that asks anything. A stop-gap until the prompt itself hands such a message back.
# The brief's form, with each word an atomic group (Python 3.11+), a word that starts another one listed first
# (heya, thank you, tysm, kk) and laughter as one word ("hahaha", "hehehe"): the brief's nested repeat took 38 s on
# "ha" x 12 and a letter (measured); this one is linear. Measured on 348,656 made-up strings of up to three words:
# with a space or a sign between the words, this one matches every string the brief's form matches, and also the
# words "haa" and "hehehe"; they differ otherwise only on words run together ("okthankso much"; mvp36/fix2/x4).
COURTESY = re.compile(
    r"^\W*(?:(?>(?:ha)+a*|(?:he){2,}e*|ok(?:ay)?|kk|k|lol|lmao|nice|cool|great|awesome|sweet|neat|wow|yay|"
    r"thank\s+you|thanks?|thx|tysm|ty|cheers|got\s+it|gotcha|hi|hello|heya|hey|yo|sup|"
    r"good\s+(?:morning|night|evening|afternoon)|goodbye|bye|see\s+ya|later|np|no\s+problem|no\s+worries|"
    r"sounds\s+good|perfect|love\s+it|there|so\s+much|a\s+lot|very\s+much|again|man|dude|bro|buddy|bot)\W*)+$", re.I)


def courtesy(text):
    return bool(COURTESY.match(text or ""))


def h2_refusal(bot, person, it, text, now):
    """Why the chat core is not tried at H2 for this interpretation: "skip" (an intent it never takes, or a second
    intent: nothing recorded, as before), a reason (recorded as not eligible), or None (tried)."""
    if getattr(it, "also", None) is not None:
        return "skip"
    intent = getattr(it, "intent", None)
    if intent in OWN_INTENTS:
        if not owns_screen(bot, person["handle"], now):
            return "skip"
    elif intent not in ASK_INTENTS:
        return "skip"
    if courtesy(text):
        return "courtesy"
    if intent == "ask" and not plain_ask(getattr(it, "spec", None)):
        return "ask_does_more"
    if intent == "clarify" and getattr(it, "draft", None) is not None:
        return "clarify_draft"   # (F06) today's clarify keeps the half-made rule as the pending question
    if profile_write(bot, person, it, text):
        return "profile_note"
    return None


FOLLOW_DECLINED = ("I can't answer that follow-up from your watch history. Try asking it as a whole question, with "
                   "the month or the channel in it.")


def at_h2(bot, person, it, text, now):
    """H2 (after the interpreter and its guards, before history.after_interpret)."""
    intent = getattr(it, "intent", None)
    try:
        why = h2_refusal(bot, person, it, text, now)
    except Exception as e:  # noqa: BLE001 - (F09) any failure of the reads before the turn: today's bot
        why = "raised:" + type(e).__name__
    if why == "skip":
        return None
    if why is not None:
        bot._tl.brain_last = {"site": "H2", "intent": intent, "decision": "not_eligible", "reason": why}
        return None
    ref = try_turn(bot, person, text, now, "H2", intent)
    if ref is None and intent == "follow_up":
        return follow_declined(bot, person, now, it, text)
    return ref


def follow_declined(bot, person, now, it=None, text=""):
    """(F08) A follow-up of the chat core's own answer, tried and declined, when that answer showed no item: today's
    follow-up would search the saves with the question against an answer it cannot read and say nothing matched.
    Code's own line instead, with no run id (the answer on screen stays the chat core's). In every other case
    (not eligible: a cap, no key; or the answer showed items today's follow-up reads) today's bot takes it.
    fix2: also today's when the turn was declined for a call to `search` or `learned` (X2: today's follow-up then
    searches the saves, as with the switch off), and when the follow-up changes an earlier pick request that is still
    kept (A2-07: today's `_changed_request` runs it again with the change, the same test `_dispatch_one` makes)."""
    d = getattr(bot._tl, "brain_last", None) or {}
    if d.get("decision") != "declined" or d.get("site") != "H2":
        return None
    if d.get("reason") == "search_or_learned":
        return None
    h = person["handle"]
    try:
        last = bot.store.last_answer(h) or {}
        if last.get("goal") != GOAL or last.get("items"):
            return None
        from .followup import request_change
        if it is not None and request_change(it, text) is not None and bot.store.get_state(f"lastspec:{h}"):
            return None
    except Exception:  # noqa: BLE001 - when in doubt, today's bot
        return None
    bot.note(intent="brain_follow_declined")
    return bot.send(h, FOLLOW_DECLINED)


def try_turn(bot, person, text, now, site, intent=None):
    """One try of the chat core for this message: the reply's reference when its answer was sent, else None (not
    eligible, or declined: today's bot then takes the message). At most once per inbound message."""
    try:
        why = not_eligible(bot, person, now)
    except Exception as e:  # noqa: BLE001 - (F09) any failure of the eligibility reads: today's bot
        why = "raised:" + type(e).__name__
    if why is not None:
        bot._tl.brain_last = {"site": site, "intent": intent, "decision": "not_eligible", "reason": why}
        return None
    bot._tl.brain_tried = True
    t0 = time.monotonic()
    h = person["handle"]
    rec = turn = prov = last = None
    reply = ids = None
    try:
        st = fresh_state(bot, h, now)
        rec, turn, prov, screen, last = run(bot, person, text, now, st)
        reason = decide(rec, turn, site, intent)
        if reason is None:
            reply, ids = render(bot, person, rec, turn)
            if not reply.parts:
                reason = "empty_reply"
    except Exception as e:  # noqa: BLE001 - any failure of the turn, the decision or the rendering: today's bot
        reason = "raised:" + type(e).__name__
    decision = {"site": site, "intent": intent, "decision": "declined" if reason else "sent", "reason": reason,
                "at": time.monotonic(), "seconds": round(time.monotonic() - t0, 3),
                "stopped_at": getattr(prov, "stopped_at", None), "shapes": shapes(rec) if rec else None}
    bot._tl.brain_last = dict(decision, rec=rec, turn=turn)
    if reason:
        return None
    return send(bot, person, rec, turn, last, reply, ids, now, decision, text)


def run(bot, person, text, now, st):
    """The turn, built as the eval builds it (eval_brain.live_conversation): the person, the bot's clock, no search
    and no learned backend, the threaded screen, window and carried topic. Every request is logged with the person."""
    tz = person.get("timezone") or "UTC"
    screen = screen_for(st, now, tz)
    last = window_of(st)
    carry = (st or {}).get("carry")
    who = {"handle": person["handle"], "library": person["library"], "timezone": tz}
    turn = TL.Turn(bot, who, now, message=text, screen="", last_window=last, search=None, learned=None,
                   carried_unlock=carry)
    prov = StopAtSearch(provider(bot))
    before = getattr(llm._tl, "person", None)
    llm._tl.person = person["handle"]   # every request's ledger row names the person, so the day's cap sees it
    try:
        rec = BL.run_turn(prov, turn, text, screen, rounds=ROUNDS, soft_s=SOFT_S, deep_s=DEEP_S, hard_s=HARD_S,
                          system=system_text(), tools=tool_list(), check=CHECK)
    finally:
        llm._tl.person = before
    return rec, turn, prov, screen, last


# ---------------------------------------------------------------- the send decision (code; the model routes nothing)
def called(rec):
    """Every tool the model called in the turn: the calls run, and the tool_use blocks of every request (a read
    refused by a time-up or during the repair is not among the calls run)."""
    out = [c.get("name") for c in rec.get("calls") or []]
    for q in rec.get("requests") or []:
        out += [b.get("name") for b in q.get("blocks") or [] if isinstance(b, dict) and b.get("type") == "tool_use"]
    return out


def _no_match(rec):
    for c in rec.get("calls") or []:
        env = c.get("result") or {}
        if env.get("error") == "no_match":
            return True
        if env.get("tool") == "find" or c.get("name") == "find":
            for row in (env.get("sheet") or {}).get("names") or []:
                if isinstance(row, dict) and row.get("status") == "no_match":
                    return True
    return False


def _counts_nothing(rec):
    """(fix2, X3) True when a result of the turn that succeeded counts nothing: `sheet.totals.items` is 0, or the
    `items` tool's `sheet.items` is an empty list."""
    for c in rec.get("calls") or []:
        env = c.get("result") or {}
        if not isinstance(env, dict) or not env.get("rid") or env.get("is_error") or env.get("error"):
            continue
        sheet = env.get("sheet")
        if not isinstance(sheet, dict):
            continue
        tot = sheet.get("totals")
        if isinstance(tot, dict) and "items" in tot and tot["items"] == 0:
            return True
        if (env.get("tool") == "items" or c.get("name") == "items") and sheet.get("items") == []:
            return True
    return False


def decide(rec, turn, site, intent=None):
    """None (send), or why the answer is not sent (today's bot then takes the message)."""
    if not isinstance(rec, dict) or not isinstance(rec.get("answer"), dict):
        return "no_record"
    ev = rec.get("events") or []
    if any(n in STOP_TOOLS for n in called(rec)):
        return "search_or_learned"
    if rec.get("error") or "provider_error" in ev or "refusal" in ev:
        return "provider"
    if any(isinstance(f, dict) and f.get("hand_back") for f in rec.get("forms") or []):
        return "hand_back"
    if rec.get("lead_source") == "plain":
        return "plain"
    if not any((c.get("result") or {}).get("rid") and not (c.get("result") or {}).get("is_error")
               for c in rec.get("calls") or []):
        return "no_result"
    if site == "H2" and intent == "ask" and _no_match(rec):
        return "no_match"
    if site == "H2" and intent == "ask" and _counts_nothing(rec):
        return "empty"   # (fix2, X3) today's search of saves may find what the history counted 0 of
    if claims(rec["answer"], turn):
        return "claimed_action"
    return None


def _names(turn):
    out = set()
    for env in (getattr(turn, "results", None) or {}).values():
        if isinstance(env, dict) and isinstance(env.get("sheet"), (dict, list)):
            out |= A._row_names(env["sheet"])
    return sorted(out, key=len, reverse=True)


def claim_sentences(answer):
    """The sentences that go out of the model's lead and points (as sent), one by one."""
    out = []
    for x in [answer.get("lead") or ""] + list(answer.get("points") or []):
        out += [s for s in V._split(str(x)) if s.strip()] or ([str(x)] if str(x).strip() else [])
    return out


def claims(answer, turn=None, names=None):
    """The sentences of the answer that say something was done or will be done ([] when none)."""
    names = _names(turn) if names is None else names
    hit = []
    for s in claim_sentences(answer):
        t = s.replace("’", "'").replace("‘", "'").replace("`", "'")
        t = _QUOTED.sub(" ", t)
        low = " ".join(t.split()).casefold()
        for n in names:
            low = re.sub(r"(?<!\w)" + re.escape(n) + r"(?!\w)", " ", low)
        low = " ".join(low.split())
        plain = low
        for rx, to in _PLAIN:
            plain = rx.sub(to, plain)
        if any(rx.search(low) or rx.search(plain) for rx in CLAIMS):
            hit.append(s)
    return hit


# ---------------------------------------------------------------- what goes out
def _plain_card(c):
    line = str(c.get("line") or "")
    if c.get("channel") and c.get("url"):
        line = line.replace(f"[{c['channel']}]({c['url']})", str(c["channel"]))
    return line


def render(bot, person, rec, turn):
    """(render.Reply, [item ids]) from the answer's fields (never its text as is): the lead, the points, code's limit
    lines, the ask line and the cards (a link part of each card's item, beside its line for channels that do not draw
    cards), the scope line, the private or carried line, the offers as words (never numbered offers)."""
    from .render import Reply, link_part
    ans = rec["answer"]
    view = bot.view(person["library"])
    ledger = V.Ledger(turn.results)
    head = ([ans["lead"]] if ans.get("lead") else []) + ["- " + p for p in ans.get("points") or []]
    head += [x for x in ans.get("limits") or [] if isinstance(x, str)]
    cards = ans.get("cards") or []
    if cards and ans.get("ask"):
        head.append(A.ASK_LINE)
    parts = [{"type": "text", "text": "\n".join(head)}] if head else []
    ids = []
    for c in cards:
        row = A._row(ledger, c.get("ref")) or {}
        iid = row.get("item_id")
        it = view.items.get(iid) if iid else None
        link = it is not None and bool(getattr(it, "url", None))
        parts.append({"type": "text", "text": "• " + _plain_card(c), **({"card_alt": True} if link else {})})
        if link:
            parts.append(link_part(it, c.get("title") or ""))
        if it is not None and iid not in ids:
            ids.append(iid)
    tail = [x for x in (ans.get("scope_line"), A.private_words(ans.get("private_line"), ans.get("carried_line")))
            if x]
    more = ["\n".join(tail)] if tail else []
    if ans.get("offers"):
        more.append(" · ".join(o["label"] for o in ans["offers"]))
    for chunk in more:
        if parts and parts[-1]["type"] == "text" and not parts[-1].get("card_alt"):
            parts[-1] = dict(parts[-1], text=parts[-1]["text"] + "\n\n" + chunk)
        else:
            parts.append({"type": "text", "text": chunk})
    return Reply(parts), ids


def shapes(rec):
    """What runs.steps keeps of a turn: tool names, counts, the lead's source, events, seconds, requests. No tool
    argument and no text."""
    calls = rec.get("calls") or []
    return {"tools": [c.get("name") for c in calls], "calls": len(calls),
            "results": sum(1 for c in calls if (c.get("result") or {}).get("rid")
                           and not (c.get("result") or {}).get("is_error")),
            "lead_source": rec.get("lead_source"), "events": list(rec.get("events") or []),
            "seconds": rec.get("seconds"), "requests": rec.get("n_requests"), "check": rec.get("check"),
            "cards": len((rec.get("answer") or {}).get("cards") or [])}


def send(bot, person, rec, turn, last, reply, ids, now, decision, text=""):
    """What a sent answer writes, as history.send_answer does, so today's follow-up reads find it; then the send.
    (fix2, A2-03) For an `unsupported` interpretation, also the request row today's dispatch writes for every one
    (`store.log_request`), so the request log is the same whoever answers."""
    from .store import now_iso
    h = person["handle"]
    if decision.get("intent") == "unsupported":
        bot.store.log_request(h, text or "", "unsupported")
    steps = {"brain": dict(shapes(rec), site=decision["site"], intent=decision["intent"], decision="sent",
                           reason=None, prompt=PROMPT_VERSION)}
    run_id = bot.store.add_run(handle=h, kind="brain", at=now_iso(now), n_candidates=len(ids), n_picks=len(ids),
                               n_dropped=0, cost_usd=float(rec.get("cost_usd") or 0.0),
                               status="picked" if ids else "none", prompt_version=PROMPT_VERSION,
                               seconds=rec.get("seconds"), steps=steps)
    bot.note(intent="brain", run_id=run_id)
    view = bot.view(person["library"])
    from . import history as Hm
    recs = []
    for k, i in enumerate(ids, 1):
        it = view.items[i]
        bot.store.add_delivery(h, None, run_id, i, k, at=now)
        recs.append({"item_id": i, "title": Hm._title(it), "url": it.url, "platform": it.platform,
                     "video_id": it.video_id, "creator": it.creator, "facts": {}, "lines": [], "line_kinds": None})
    bot.store.set_last_answer(h, run_id, None, list(ids), GOAL)
    bot.store.set_state(f"lines:{h}", {i: [] for i in ids})
    bot.store.set_state(f"linekinds:{h}", {i: None for i in ids})
    bot.store.set_state(f"facts:{h}", {i: {} for i in ids})
    bot._keep_answer(run_id, h, None, GOAL, "history", reply, recs)
    win = BL.last_window(turn, rec) or last
    bot.store.set_state(STATE.format(h=h), {
        "run_id": run_id, "at": now_iso(now), "screen": BL.screen_after(rec),
        "window": win.model_dump(mode="json") if win is not None else None,
        "carry": BL.unlock_after(turn, rec)})
    return bot.send(h, reply, run_id)


def ledger_purpose_rows(path=None):
    """Rows of the MVP ledger with this module's purpose (for checks; counts only are reported)."""
    path = path or llm.ai.LEDGER
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [r for r in (json.loads(x) for x in f if x.strip()) if r.get("purpose") == PURPOSE]
