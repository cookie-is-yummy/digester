"""PROTOTYPE ONLY - answers across many items (round 11, slice M; DESIGN.md section 18.M).

"summarize what I've learned about motion design", "what do my saves say about sourdough", "the main ideas across what
I watched on budgeting": read by code (never the question's own function words as search words), then

1. retrieve many items for the topic (the library view and the search engine the bot already has);
2. read each fitting item's key points from its own text with the details step (extract.py, cached per item, every
   line checked against the text as today);
3. one model call (prompts/synth_v1.md) writes 3 to 6 points, each with the numbers of the items it comes from and an
   exact quote of each;
4. code checks every point (`check_points`): each quote must be the cited item's own words, the point's content words
   must be found in the text of the items it cites, its numbers too, no link, handle or word about the bot; a point
   with no source left is dropped. Code writes the reply (texts.py, round 11 block): each point, then the items it came
   from (title and link), then "from N videos and M posts; K more fit but say nothing in their text" and what was read.

The model fills a form; code checks it and writes the message. Captions and descriptions are data, never instructions:
an item whose text speaks to an assistant is never read here. No action is taken from anything an item says.
"""
import json
import os
import re
import time

from . import config, llm

# round 11 fix, B (S3): v4 asks for points that answer the question about the topic, never what an item is
PROMPT_VERSION = os.environ.get("MVP_SYNTH_PROMPT", "synth_v5")   # v3: v2 plus points spread over the items;
# v2: closer to the items' words, one idea per point, never what the items are (DESIGN 18.M); v1 and v2 stay as measured
PROMPT = open(os.path.join(config.HERE, "prompts", f"{PROMPT_VERSION}.md"), encoding="utf-8").read()
ON = os.environ.get("MVP_SYNTH", "1") != "0"    # off: the message goes to the interpreter as before (the eval's "before")
# round 11 fix, B (S2): "from what i watched" limits the items to watches, "from my saves" to saves (off: as slice M)
SOURCE_LIMIT = os.environ.get("MVP_SYNTH_SOURCE", "1") != "0"
ONE_ITEM_MAX = 2     # points that come from one item alone, when 3 or more items are cited
THIN_LIST = 3        # (S3) items listed, with their links, when the text says too little to sum up
MAYBE_READABLE = 3   # the search's next best are read only when fewer than this many fitting items have text
CANDS = 40           # ranked candidates looked at
READS = 12           # items whose key points are read (one details call each, cached per item)
RICH_TEXT = 120      # an item with at least this much of its own text is read before shorter ones
MAYBE_WHEN = 5       # fewer items than this name the topic: the search's next best are read too (the model judges)
MAYBE_READS = 8      # at most this many items read in all when that happens
MAX_POINTS = 6
MIN_POINTS = 2       # fewer checked points than this: the plain list of what fits, with no summary
TRACE_MIN = 0.6      # share of a point's content words that must be found in the text of the items it cites
QUOTE_MIN_WORDS = 3
POINT_MAX_CHARS = 260
SHOW_SOURCES = 3     # items named under one point
TEMPERATURE = 0
SEED = 7

# ---------- the read (code only) ----------
_LEAD = (r"^\W*(?:(?:so|ok|okay|hey|hi|and|um+|hmm+)[,\s]+)*"
         r"(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?|please\s+|pls\s+|now\s+)?"
         r"(?:(?:tell|show|give|send)\s+me\s+)?")
_I = r"i(?:'ve|’ve|ve|\s+have)?"
_KEPT_VERB = r"(?:learned|learnt|picked\s+up|watched|saved|kept|liked|seen|found|bookmarked)"
_SUMMARY = (r"(?:summari[sz]e|sum\s+up|(?:a\s+)?(?:quick\s+|short\s+|brief\s+)?(?:summary|rundown|overview|recap)"
            r"\s+of)")
_OBJ = (r"(?:my\s+(?:saves|saved\s+(?:posts|videos|reels|stuff)|videos|reels|likes|library|watch\s+history|history)|"
        r"(?:what|everything|all(?:\s+that)?|the\s+(?:videos|posts|reels|ones|stuff|things))\s+" + _I + r"\s+"
        + _KEPT_VERB + r")")
_ABOUT = r"(?:about|on|regarding|around)"
_SOURCE_TAIL = (r"(?:\s+(?:from|in|across|among)\s+" + _OBJ + r"(?:\s+(?:so\s+far|on\s+(?:youtube|instagram)))?"
                r"|\s+so\s+far|\s+on\s+(?:youtube|instagram)|\s+for\s+me)*")
_END = r"\s*[?.!]*\s*$"
_TOPIC = r"(?P<topic>[^?.!]{2,80}?)"

FORMS = [
    # "summarize what I've learned about X (from what I watched)", "a summary of my saves on X"
    re.compile(_LEAD + _SUMMARY + r"\s+(?:for\s+me\s+)?(?:" + _OBJ + r"|what\s+" + _I + r"\s+learn(?:ed|t)?)\s+"
               + _ABOUT + r"\s+" + _TOPIC + _SOURCE_TAIL + _END, re.I),
    # "summarize X from what I watched" (a source is required: "summarize the pasta one" stays a question on a pick)
    re.compile(_LEAD + _SUMMARY + r"\s+(?:for\s+me\s+)?(?:everything\s+)?(?:about\s+)?" + _TOPIC
               + r"\s+(?:from|in|across|among)\s+" + _OBJ + r"(?:\s+so\s+far)?" + _END, re.I),
    # "what have I learned about X", "what did I learn about X", "tell me what I've learned about X"
    re.compile(_LEAD + r"what\s+(?:have|did|do)\s+i\s+(?:learn|learned|learnt|pick\s+up|picked\s+up|know)\s+"
               + _ABOUT + r"\s+" + _TOPIC + _SOURCE_TAIL + _END, re.I),
    re.compile(_LEAD + r"what\s+i(?:'ve|’ve|ve|\s+have)\s+(?:learned|learnt|picked\s+up)\s+" + _ABOUT + r"\s+"
               + _TOPIC + _SOURCE_TAIL + _END, re.I),
    # "what do my saves say about X", "what do the videos I watched say about X"
    re.compile(_LEAD + r"what\s+do(?:es)?\s+(?:all\s+)?(?:my\s+(?:saves|videos|reels|likes|library)|the\s+(?:videos|posts|"
               r"reels|ones)\s+" + _I + r"\s+" + _KEPT_VERB + r")(?:\s+all)?\s+(?:say|teach\s+me|tell\s+me)\s+"
               + _ABOUT + r"\s+" + _TOPIC + _SOURCE_TAIL + _END, re.I),
    # "the main ideas across what I watched on X", "key takeaways from my saves about X"
    re.compile(_LEAD + r"(?:what\s+are\s+)?(?:the\s+)?(?:main|key|big|biggest|common|top)\s+(?:ideas|takeaways|points|"
               r"lessons|themes|tips)\s+(?:across|in|from|among)\s+" + _OBJ + r"\s+" + _ABOUT + r"\s+" + _TOPIC
               + _SOURCE_TAIL + _END, re.I),
    re.compile(_LEAD + r"(?:what\s+are\s+)?(?:the\s+)?(?:main|key|big|biggest|common|top)\s+(?:ideas|takeaways|points|"
               r"lessons|themes|tips)\s+" + _ABOUT + r"\s+" + _TOPIC + r"\s+(?:across|in|from|among)\s+" + _OBJ
               + r"(?:\s+so\s+far)?" + _END, re.I),
]
# "what do these say", "what do those videos all say about X", "summarize all of these": over the last answer's items
THESE = re.compile(_LEAD + r"(?:what\s+do\s+(?:all\s+)?(?:these|those)(?:\s+(?:videos|posts|reels|ones|saves))?(?:\s+all)?"
                   r"\s+(?:say|teach\s+me|tell\s+me)(?:\s+" + _ABOUT + r"\s+" + _TOPIC + r")?|"
                   + _SUMMARY + r"\s+(?:all\s+(?:of\s+)?)(?:these|those|them)(?:\s+(?:videos|posts|reels|ones))?)"
                   + _END, re.I)
# a time, a repeat or an action anywhere: a rule, a reminder or a history question with a window (slice H), never this
NOT_HERE = re.compile(
    r"\b(?:every|each|daily|weekly|monthly|nightly|tomorrow|tonight|today|yesterday|lately|recently|ago|since|until|"
    r"this\s+(?:week|month|year|morning|evening|weekend)|last\s+(?:week|month|year|night|weekend|\d+)|"
    r"past\s+(?:week|month|year|few|\d+)|next\s+(?:week|month|year|time)|"
    r"in\s+(?:19|20)\d\d|(?:january|february|march|april|june|july|august|september|october|november|december)|"
    r"(?:mon|tues|wednes|thurs|fri|satur|sun)days?|at\s+\d|\d\s*(?:am|pm)\b|o'?clock|"
    r"remind|email|e-mail|text\s+me|calendar|schedule|to-?dos?|my\s+(?:list|notes)|whenever|when\s+i|"
    r"how\s+many|how\s+much|first|last\s+time|most|top\s+\d|rank)\b", re.I)
_TOPIC_TRIM = re.compile(r"(?:\s+(?:so\s+far|for\s+me|please|pls|on\s+(?:youtube|instagram)|in\s+general|overall|"
                         r"from\s+(?:youtube|instagram)))+$", re.I)
_TOPIC_LEAD = re.compile(r"^(?:the\s+(?:topic\s+(?:of\s+)?)?|topic\s+of\s+)", re.I)
NOT_TOPIC = set("""me myself you yourself it this that these those them they everything anything something stuff things
thing my your rules rule reminders reminder list lists data account privacy settings export bot app saves videos posts
reels likes library history what all life""".split())
BOT_WORDS = re.compile(r"\b(?:rules?|reminders?|to-?dos?|lists?|my\s+data|account|privacy|settings|exports?|"
                       r"the\s+bot|you)\b", re.I)


def _source(text):
    """(platforms, kinds) the message limits the items to. "watched" and "my saves" limit nothing: a reel watched and
    kept is a video the person watched too, and the bot itself calls everything kept "your saves" (DESIGN 18.M).
    "liked" is read as likes only."""
    t = text.lower()
    platforms = []
    if re.search(r"\b(?:on|from)\s+youtube\b", t):
        platforms = ["youtube"]
    elif re.search(r"\b(?:on|from)\s+instagram\b", t):
        platforms = ["instagram"]
    kinds = []
    if re.search(r"\b(?:i(?:'ve|’ve|ve|\s+have)?\s+liked|my\s+likes)\b", t):
        kinds = ["like"]
    return platforms, kinds


def clean_topic(raw):
    t = " ".join((raw or "").split()).strip(" ,;:-\"'“”‘’")
    t = _TOPIC_TRIM.sub("", t)
    t = _TOPIC_LEAD.sub("", t).strip(" ,;:-\"'“”‘’")
    return t


def topic_ok(topic):
    words = re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", topic.lower())
    if not 1 <= len(words) <= 6:
        return False
    if all(w in NOT_TOPIC for w in words) or BOT_WORDS.search(topic):
        return False
    return True


# ---------- the merge of round 11 (DESIGN 18, seam b): a time window, read with slice H's window words ----------
def _how(t):
    """watched | liked | saved | any: what the message says the person did with the items."""
    t = t.lower()
    if re.search(r"\b(?:liked|likes)\b", t):
        return "liked"
    # round 11 fix, B (S2): "what i watched and saved" limits nothing
    if re.search(r"\bwatch(?:ed|ing)?\b", t) and re.search(r"\b(?:saved|saves|bookmarked)\b", t):
        return "any"
    if re.search(r"\bwatch(?:ed|ing)?\b", t):
        return "watched"
    if re.search(r"\b(?:saved|saves|bookmarked)\b", t):
        return "saved"
    return "any"


def _window_cut(t, today):
    """(the message without its one time window, the Window) or None. Only a plain window ("last month", "in
    October", "this year", "since March", "lately"); anything else NOT_HERE stops (a repeat, a reminder, "first",
    "most", "how many") still stops the read."""
    from .history import Window, find_windows, normal
    n = normal(t)
    wins = find_windows(n, today)
    if len(wins) != 1 or not isinstance(wins[0][0], Window):
        return None
    (w, (a, b)), = wins
    rest = " ".join((n[:a] + " " + n[b:]).split())
    if NOT_HERE.search(rest):
        return None
    return rest, w
# ---------- end the merge of round 11 ----------


def read(text, today=None):
    """The request read from the message, or None: {"topic", "platforms", "kinds", "these", "window", "how"}. Code
    only; English only. With `today`, one time window is read too (the merge of round 11) and the items are limited
    to what the person watched, liked or saved in it (slice H's record)."""
    t = " ".join((text or "").split())
    if not t or len(t) > 220:
        return None
    window = None
    if NOT_HERE.search(t):
        got = _window_cut(t, today) if today is not None else None
        if got is None:
            return None
        t, window = got
    req = _read(t)
    if req is not None and window is not None and req["these"]:
        return None   # "what do these say last month": not a summary of the answer in view
    if req is not None:
        req.update(window=window, how=_how(t))
    return req


# ---------- round 11 fix, B (V1): "ask my videos about X": the summary of what was watched, then the offer ----------
ASK_MINE = re.compile(_LEAD + r"ask\s+(?:all\s+)?my\s+(?:youtube\s+)?(?:videos|vids|watch\s+history)\s+"
                      r"(?:what\s+they\s+say\s+)?" + _ABOUT + r"\s+" + _TOPIC + _END, re.I)


def read_ask_mine(text):
    """The summary request of "ask my videos about X" (the videos watched; the reply offers "ask them"), or None.
    Only while MVP_VIDEO_ASK=1: with it off the message goes on as before."""
    from . import videoask
    if not videoask.on():
        return None
    t = " ".join((text or "").split())
    if not t or len(t) > 220 or NOT_HERE.search(t):
        return None
    m = ASK_MINE.match(t)
    if not m:
        return None
    topic = clean_topic(m.group("topic"))
    if not topic or not topic_ok(topic):
        return None
    return {"topic": topic, "platforms": [], "kinds": [], "these": False, "window": None, "how": "watched"}
# ---------- end round 11 fix, B ----------


def _read(t):
    m = THESE.match(t)
    if m:
        topic = clean_topic(m.group("topic") or "")
        if topic and not topic_ok(topic):
            return None
        platforms, kinds = _source(t)
        return {"topic": topic or None, "platforms": platforms, "kinds": kinds, "these": True}
    for rx in FORMS:
        m = rx.match(t)
        if not m:
            continue
        topic = clean_topic(m.group("topic"))
        if not topic or not topic_ok(topic):
            return None
        platforms, kinds = _source(t)
        return {"topic": topic, "platforms": platforms, "kinds": kinds, "these": False}
    return None


# ---------- which candidates fit (code) ----------
STOP = set("""a an and the of for to in on with my your our this that is it at by from or as be are was were how what why
when where which who i me you we they about into over under more most some any all very just really good best
basics basic tips tip tricks trick ideas idea things thing stuff guide guides learn learning videos video posts post
reels reel""".split())
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def content_words(text):
    return [w for w in _WORD.findall((text or "").lower()) if w not in STOP and (len(w) >= 3 or w.isdigit())]


def _base(word):
    """'stretching' -> 'stretch', 'budgeting' -> 'budget', 'running' -> 'run' (so a topic said as an activity finds
    posts that name the thing); other words as they are."""
    if len(word) > 6 and word.endswith("ing"):
        b = word[:-3]
        return b[:-1] if len(b) > 2 and b[-1] == b[-2] and b[-1] not in "ls" else b
    return word


def fits_topic(text, topic):
    """True when the item's own text names the topic: the phrase, or every content word of a short topic (2 of 3 or
    more for a longer one), each as a whole word in singular or plural (retrieve.contains_word)."""
    from .retrieve import contains_word
    if contains_word(text, topic):
        return True
    words = list(dict.fromkeys(content_words(topic)))
    if not words:
        return False
    found = sum(1 for w in words if contains_word(text, w) or (_base(w) != w and contains_word(text, _base(w))))
    need = len(words) if len(words) <= 2 else max(2, (2 * len(words) + 2) // 3)
    return found >= need


# ---------- the checks on the model's points (code) ----------
def _stem(w):
    w = w.lower()
    for suf in ("ings", "ing", "ies", "es", "ed", "ly", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[:-len(suf)]
    return w


def _keyset(text):
    out = set()
    for w in _WORD.findall((text or "").lower()):
        if len(w) >= 3 or w.isdigit():
            out.add(_stem(w)[:6])
    return out


def trace_share(point, texts):
    """Share of the point's content words (stemmed, first 6 letters) found among the words of `texts`."""
    words = [w for w in content_words(point) if not w.isdigit()]
    if not words:
        return 0.0
    have = set()
    for t in texts:
        have |= _keyset(t)
    return sum(1 for w in words if _stem(w)[:6] in have) / len(words)


_LEADING_MARK = re.compile(r"^\s*(?:\d{1,2}\s*[.)\-:]|[-*•·]+)\s*")
_ABOUT_ITEM = re.compile(r"\b(?:this|the|that)\s+(?:video|post|reel|item|creator|caption|description)\b|\bitems?\b|"
                         r"\b(?:subscribe|follow\s+(?:me|us|for)|link\s+in\s+bio|use\s+code)\b", re.I)


# ---------- round 11 fix, B (S3): a point that says what an item is, not what it says ----------
_KIND_NOUN = (r"(?:tutorials?|videos?|vids?|guides?|courses?|clips?|reels?|posts?|creators?|lessons?|walkthroughs?|"
              r"breakdowns?|channels?|vlogs?|explainers?|series|sources?|resources?|episodes?|streams?|livestreams?|"
              r"items?|captions?|descriptions?|titles?|recaps?|tier\s+lists?|reviews?)")
_KIND_VERB = (r"(?:(?:is|are|was|were)\s+(?:all\s+|mostly\s+|also\s+)?(?:suitable|aimed|meant|designed|made|geared|"
              r"tailored|targeted|intended|ideal|perfect|great|good|useful|helpful|available|focused|dedicated|"
              r"beginner|beginner-friendly|for|about|part|explained|ranked|shared|listed|posted|a\s+(?:vlog|recap|series|"
              r"tier\s+list|tutorial|walkthrough))|"
              r"(?:also\s+|mainly\s+|mostly\s+)?(?:focus|focuses|cover|covers|show|shows|showcase|showcases|"
              r"demonstrate|demonstrates|feature|features|include|includes|walk|walks|offer|offers|introduce|"
              r"introduces|discuss|discusses|provide|provides|explore|explores|highlight|highlights|present|presents|"
              r"go\s+over|goes\s+over|talk\s+about|talks\s+about|review|reviews|compare|compares|exist|exists|"
              r"rank|ranks|follow|follows|document|documents|teach|teaches)\b(?!\s+(?:that|why)\b))")
# a quote in which the item's maker says what the item is or does ("In this tutorial, I break down ...", "I explore
# workflow, easing ...", "suitable for beginners"): it cannot answer what the item says about a thing asked
SELF_DESCRIBED = re.compile(
    r"\b(?:in\s+this\s+(?:[\w'-]+\s+){0,3}(?:tutorial|video|episode|course|lesson|class|stream|vlog|series|post|reel)|"
    r"this\s+(?:[\w'-]+\s+){0,2}(?:tutorial|video|course|series)\s+(?:is|covers|shows|explains|will|goes)|"
    r"i\s+(?:explore|break\s+down|show\s+you|walk\s+you|go\s+over|cover|talk\s+about|demonstrate|share\s+how|"
    r"use\s+a\s+(?:simple|quick|easy))|we(?:'ll|\s+will)\s+(?:explore|cover|look\s+at|go\s+over|learn)|"
    r"you(?:'ll|\s+will)\s+learn|suitable\s+for|for\s+(?:complete\s+|absolute\s+)?beginners|"
    r"i'?m\s+(?:uploading|launching|planning|going\s+to\s+show)|follow[- ]up\s+parts?|part\s+\d+\s+of)\b", re.I)
META = re.compile(
    r"^(?:(?:several|some|many|most|a\s+few|few|two|three|four|five|both|all|these|those|the|one|other|each|"
    r"certain|various|multiple)\s+(?:of\s+(?:the|these|them)\s+)?)?(?:[\w'-]+\s+){0,3}?" + _KIND_NOUN + r"\s+"
    + _KIND_VERB
    + r"|^there\s+(?:is|are)\s+(?:a|an|one|two|three|several|some|many|a\s+few)\s+(?:[\w'-]+\s+){0,3}?" + _KIND_NOUN
    + r"|\b(?:is|are)\s+(?:suitable|aimed|meant|designed|geared|tailored|targeted|intended)\s+(?:at|for)\b"
    + r"|\b(?:suitable|perfect|ideal|great)\s+for\s+(?:complete\s+|absolute\s+|total\s+)?(?:beginners|newcomers|"
      r"novices|everyone|anyone|all\s+levels)\b"
    + r"|\bfor\s+(?:motion\s+designers|creators|artists)\s+of\s+(?:every|all)\s+levels?\b"
    + r"|^[\w\s'-]{0,40}\b(?:is|are)\s+(?:all\s+)?about\s+(?:shooting|making|doing|watching|having|sharing)\b"
    + r"|\b(?:can|could)\s+be\s+(?:ranked|rated|sorted|listed|explained|shared|found|watched)\b"
    + r"|\b(?:is|are)\s+explained\s+(?:for|to|in)\b"
    + r"|\b(?:is|are)\s+(?:a|an|just\s+a)\s+(?:vlog|recap|tier\s+list|series|walkthrough|livestream|dump|tour|"
      r"reaction|compilation|montage)\b"
    + r"|\bpersonal\s+experience\b|\bnot\s+a\s+tutorial\b|\bfirst\s+(?:week|year|month|day)\s+(?:of|learning)\b",
    re.I)


def _defines_topic(text, topic):
    """True for "<topic> can be a day in the city", "<topic> is all about ...": what the topic is, not what it says."""
    if not topic:
        return False
    rx = (r"^(?:the\s+)?" + re.escape(topic.lower()) + r"s?\s+(?:can\s+(?:be|mean)|is|are|was|were)\s+(?:a|an|about|"
          r"all\s+about|just|mostly|really)\b")
    return bool(re.match(rx, text.lower()))


def _root(w):
    """'easing', 'ease', 'easy', 'eased' -> 'eas'; 'lighting', 'lights' -> 'light'."""
    w = w.lower()
    for suf in ("ings", "ing", "ed", "es", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            w = w[:-len(suf)]
            break
    return w[:-1] if len(w) > 3 and w[-1] == "e" else w


def off_question(text, topic):
    """True when the topic asks about one thing inside a subject ("easing in after effects") and the point never
    names that thing: it may be about the subject, but it does not answer the question."""
    thing, ctx = focus(topic)
    if not ctx:
        return False
    want = {_root(w) for w in content_words(thing)}
    have = {_root(w) for w in _WORD.findall((text or "").lower())}
    return not any(a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)))
                   for a in want for b in have)


def _title_only(text, titles, topic):
    """True when every content word of the point, the topic's own words aside, is a word of one cited item's title:
    the title said again as a sentence ("Knife skills for beginners.")."""
    tw = {_stem(w)[:6] for w in content_words(topic or "")}
    words = {_stem(w)[:6] for w in content_words(text)} - tw
    if not words:
        return True
    if len(words) > 3:   # a sentence with more to it than a label is kept, even when the caption is one line
        return False
    return any(words <= {_stem(w)[:6] for w in content_words(t)} for t in titles)
# ---------- end round 11 fix, B ----------


def check_points(raw, items, extra=None, notes=None, need_about=(), topic=None):
    """(points, dropped): the model's points that code can trace to the text of the items they cite.

    `items` is the numbered list the model saw (1-based). A point is kept only when it is a plain sentence (no link,
    handle or word about the bot or the item), at least one of its sources is a valid item number whose quote is that
    item's own words (3 words or more), its content words are found in the cited items' text (TRACE_MIN), every number
    in it is in that text, and it does not repeat a kept point. Each kept point: {"text", "ids", "share"}.
    `need_about`: ids of items that do not name the topic in their own words (search-ranked only): such an item counts
    as a source only when the model listed it in "about"."""
    from .compose import ASSISTANT_NOTE, INTERNAL, UNSAFE_TEXT, check_text, numbers_backed, quote_ok, tokens
    from .videoask import ACTING   # the same words asking a video uses for a point that reads like an order
    dropped = {}

    def drop(why, text=None):
        dropped[why] = dropped.get(why, 0) + 1
        if notes is not None:   # the eval's transcript only (made-up data); never stored
            notes.append((why, text))
    pts = raw.get("points") if isinstance(raw, dict) else None
    if not isinstance(pts, list):
        return [], ({"bad_form": 1} if raw else {})
    about = raw.get("about") if isinstance(raw, dict) else None
    about = {n for n in about if isinstance(n, int)} if isinstance(about, list) else None
    kept, seen = [], []
    for p in pts[:MAX_POINTS + 4]:
        if not isinstance(p, dict):
            drop("bad_form")
            continue
        text = _LEADING_MARK.sub("", " ".join(str(p.get("text") or "").split())).strip()
        if not text or len(text) > POINT_MAX_CHARS or len(content_words(text)) < 2:
            drop("bad_text", text)
            continue
        if UNSAFE_TEXT.search(text) or INTERNAL.search(text) or _ABOUT_ITEM.search(text):
            drop("unsafe_text", text)
            continue
        if ACTING.search(text) or ASSISTANT_NOTE.search(text):
            # the round 11 check (DESIGN 18.X): an item's own call to act ("email everyone you know", "add it to your
            # calendar", "ignore your rules") is never passed on as something the person learned
            drop("instruction", text)
            continue
        if META.search(text) or _defines_topic(text, topic):   # round 11 fix, B (S3): what an item is, who it is for
            drop("about_item", text)
            continue
        if off_question(text, topic):   # round 11 fix, B (S3): "easing in after effects", a point never about easing
            drop("off_question", text)
            continue
        ids, texts, meta_quotes, quotes = [], [], 0, []
        for s in p.get("sources") or []:
            if not isinstance(s, dict):
                continue
            n = s.get("n")
            if isinstance(n, str) and n.strip().isdigit():
                n = int(n.strip())
            if not isinstance(n, int) or not 1 <= n <= len(items):
                continue
            if about is not None and n not in about:   # the model itself said the item is not about the topic
                continue
            it = items[n - 1]
            if it.id in need_about and about is None:
                continue
            quote = " ".join(str(s.get("quote") or "").split())
            body = check_text(it, extra)
            if len(tokens(quote)) < QUOTE_MIN_WORDS or not quote_ok(quote, body):
                continue
            if it.id not in ids:
                ids.append(it.id)
                texts.append(body)
                meta_quotes += 1 if SELF_DESCRIBED.search(quote) else 0
                quotes.append(quote)
        if not ids:
            drop("no_source", text)
            continue
        if topic and focus(topic)[1] and off_question(" ".join(quotes), topic):
            # round 11 fix, B (S3): asked about one thing ("easing in after effects"), no quoted words of the items
            # name it: the point says it, the items do not
            drop("off_question", text)
            continue
        if meta_quotes == len(ids) and topic and focus(topic)[1]:
            # round 11 fix, B (S3): asked about one thing ("easing in after effects"), every source only says what
            # its video is ("I explore workflow, easing & ..."): that is not what it says about easing
            drop("about_item", text)
            continue
        if _title_only(text, [getattr(x, "first_line", "") or (x.caption or "").split("\n")[0]
                              for x in items if x.id in ids], topic):   # round 11 fix, B (S3): an item's title said again is not something it says
            drop("title_only", text)
            continue
        share = trace_share(text, texts)
        if share < TRACE_MIN:
            drop("not_traced", text)
            continue
        if not numbers_backed(text, "\n".join(texts)):
            drop("number_not_in_text", text)
            continue
        keys = _keyset(" ".join(content_words(text)))
        if any(len(keys & k) >= 0.8 * max(1, min(len(keys), len(k))) for k in seen):
            drop("repeat", text)
            continue
        seen.append(keys)
        kept.append({"text": text if text.endswith((".", "!", "?")) else text + ".", "ids": ids, "share": round(share, 2)})
        if len(kept) >= MAX_POINTS:
            break
    return kept, dropped


# ---------- round 11 fix, B (S2): no more than 2 points from one item when 3 or more items are cited ----------
def spread(points, dropped=None, notes=None):
    """The points with the third and later of those that come from one item alone left out, when the points cite 3
    items or more (a point with several sources is from all of them and always stays)."""
    if len({i for p in points for i in p["ids"]}) < 3:
        return points
    alone, out = {}, []
    for p in points:
        if len(p["ids"]) == 1:
            n = alone.get(p["ids"][0], 0)
            if n >= ONE_ITEM_MAX:
                if dropped is not None:
                    dropped["one_item"] = dropped.get("one_item", 0) + 1
                if notes is not None:
                    notes.append(("one_item", p["text"]))
                continue
            alone[p["ids"][0]] = n + 1
        out.append(p)
    return out


_FOCUS = re.compile(r"^(?P<thing>[^\W\d_][\w'-]*(?:\s+[\w'-]+){0,2}?)\s+(?:in|for|with|using|inside|on)\s+"
                    r"(?P<ctx>[\w'-]+(?:\s+[\w'-]+){0,3})$", re.I)


def focus(topic):
    """(the thing asked about, the subject it sits in) for "easing in after effects", else (topic, None)."""
    m = _FOCUS.match(" ".join((topic or "").split()))
    if not m or not content_words(m.group("thing")) or not content_words(m.group("ctx")):
        return topic, None
    return m.group("thing"), m.group("ctx")


def _did(it, how_kinds):
    return bool((set(it.kinds) | set(getattr(it, "dates", {}) or {})) & set(how_kinds))


def lead_words(how, items):
    """What was read, for the reply's lead: "the videos you watched", "the posts you saved", "the posts and videos you
    watched and saved". Never "kept" for a watch."""
    from .history import HOW_KINDS
    yt = sum(1 for it in items if it.platform == "youtube")
    noun = "videos" if yt == len(items) else "posts" if not yt else "posts and videos"
    if how == "watched":
        return "the videos you watched"
    if how in ("saved", "liked"):
        return f"the {noun} you {how}"
    watched = [it for it in items if _did(it, HOW_KINDS["watched"])]
    if items and len(watched) == len(items):
        return "the videos you watched"
    if not watched:
        return f"the {noun} you saved"
    return f"the {noun} you watched and saved"


def _limit(bot, person, req):
    """The request limited to what the person watched, saved or liked when the message says so ("from what i
    watched", "the videos i watched", "my watch history", "from my saves")."""
    from . import history as Hs
    how = req.get("how") or "any"
    if not SOURCE_LIMIT or how == "any" or req.get("these") or req.get("only") is not None:
        return req
    kinds = set(Hs.HOW_KINDS[how])
    view = bot.view(person["library"])
    # the merge of round 11's fixes (seam c): "watched" means what slice H's record counts as watched (a watch or a
    # view event, in the person's time zone, never a friend's share), the same record a history answer reads
    rec = Hs.record(view, person.get("timezone") or "UTC")
    dates = {}
    for iid, evs in rec.events.items():
        if view.items.get(iid) is None:
            continue
        ds = [d for d, k in evs if k in kinds]
        if ds:
            dates[iid] = max(ds).isoformat()
    # and fix A's fit (R3) where the library has its item vectors: an item that holds the topic's words but whose
    # vector is far from the others that hold them is left out ("mentions it but isn't about it"); items that don't
    # hold the words are left to the search. No vectors, or too few items to tell: nothing changes.
    unfit = set()
    words = Hs.content_words(req.get("topic") or "")
    if 0 < len(words) <= 4:
        fit = Hs.topic_fit(view, rec, " ".join(words))
        if fit is not None:
            unfit = {i for i in dates if i in fit[0] and fit[0][i] < fit[1]}
    for i in unfit:
        dates.pop(i, None)
    return dict(req, only=set(dates), dates=dates, unfit=len(unfit))
# ---------- end round 11 fix, B ----------


# ---------- the call ----------
def _block(n, it, lines):
    from .compose import as_data, display_title
    body = "Title: " + display_title(it) + "\nPoints from its own text:\n" + "\n".join("- " + x for x in lines)
    return f"{n}. " + as_data(body)


def call(topic, items, points_of, person=None):
    """One model call over the numbered items. Returns (raw, cost)."""
    thing, ctx = focus(topic)   # round 11 fix, B (S3): "easing in after effects" asks about easing
    asked = ("\nAsked about: " + json.dumps(thing, ensure_ascii=False)) if ctx and PROMPT_VERSION >= "synth_v4" else ""
    user = ("Topic: " + json.dumps(topic, ensure_ascii=False) + asked + "\n\nItems:\n\n"
            + "\n\n".join(_block(i, it, points_of[it.id]) for i, it in enumerate(items, 1)))
    return llm.chat_json(PROMPT, user, purpose="mvp_synth", prompt_version=PROMPT_VERSION, person=person,
                         max_tokens=1400, temperature=TEMPERATURE, seed=SEED)


# ---------- the run ----------
def _spec(topic, platforms, kinds):
    from .schema import RuleSpec
    return RuleSpec.model_validate({"when": {"type": "now"}, "content": {
        "source": "library", "goal": topic[:200], "searches": [topic[:200]], "count": 1, "platforms": platforms,
        "kinds": kinds}})


def gather(bot, person, req, now, last=None):
    """(fits, maybes, extra, steps, cost): the items whose own text names the topic, best first; the other ranked
    candidates (the search's own order), read only when few name it; the YouTube descriptions."""
    from . import captionmark
    from .compose import ASSISTANT_NOTE, collapse_copies, own_text
    from .retrieve import candidates
    h = person["handle"]
    view = bot.view(person["library"])
    steps, cost = {}, 0.0
    if req.get("unfit"):   # the merge of round 11's fixes (seam c): left out of a limited summary by fix A's fit
        steps["unfit"] = req["unfit"]
    cfb = captionmark.index(bot.store.caption_feedback(h))
    if req.get("these"):
        cands = [x for x in (view.get(i) for i in (last or {}).get("items") or []) if x is not None]
    else:
        ex_kinds, ex_platforms = bot._exclusions(h)
        spec = _spec(req["topic"], req.get("platforms") or [], req.get("kinds") or [])
        only = req.get("only")   # the merge of round 11: the items of the window (slice H's record), when one was said
        cands, meta = candidates(bot.pool, view, spec, disliked=bot.store.disliked(h), now=now, store=bot.store,
                                 exclude_kinds=ex_kinds, exclude_platforms=ex_platforms, k=CANDS, caption_fb=cfb,
                                 only=only)
        cost += meta.get("cost_usd", 0.0)
        if only is not None and len(cands) < CANDS:
            # the search ranks the whole library and then keeps the window's items, so a window's items that name
            # the topic in their own words are added after them, newest first (code fit, as below)
            have = {c.id for c in cands} | set(bot.store.disliked(h))
            more = [view.get(i) for i in sorted(only, key=lambda i: req["dates"].get(i, ""), reverse=True)
                    if i not in have]
            cands += [x for x in more if x is not None and fits_topic(own_text(x, {}), req["topic"])][:CANDS - len(cands)]
    extra = bot._youtube().details(cands, now=now) if any(c.platform == "youtube" for c in cands) else {}
    cands, n_copies = collapse_copies(cands, extra)
    if n_copies:
        steps["copies"] = n_copies
    fits, maybes = [], []
    for it in cands:
        own = own_text(it, extra)
        if captionmark.effective(it, cfb)[0] == "strong":   # a caption that may not be the video's: never read here
            steps["strong_left_out"] = steps.get("strong_left_out", 0) + 1
            continue
        if ASSISTANT_NOTE.search(own):   # text that speaks to an assistant is data we do not read at all
            steps["note_left_out"] = steps.get("note_left_out", 0) + 1
            continue
        if req.get("these") or fits_topic(own, req["topic"]):
            fits.append(it)
        else:
            maybes.append(it)
    steps["candidates"], steps["fit"] = len(cands), len(fits)
    return fits, maybes, extra, steps, cost


def summarize(bot, person, req, now, last=None):
    """The synthesis for one request: a dict for texts.synth_message, plus the run's facts."""
    from .compose import own_text_lines
    from .extract import MIN_TEXT, details_many
    t0 = time.time()
    h = person["handle"]
    fits, maybes, extra, steps, cost = gather(bot, person, req, now, last=last)
    view = bot.view(person["library"])
    # the items with the most of their own text are read first (search order otherwise): a bare title says little
    readable = sorted([it for it in fits if len(own_text_lines(it, extra)) >= MIN_TEXT],
                      key=lambda it: len(own_text_lines(it, extra)) < RICH_TEXT)[:READS]
    maybe = []
    # round 11 fix, B: only when fewer than 3 items that name the topic have text to read (3 or more make a summary
    # on their own; reading nearby items then brought in posts about something close by, a workout for "strength
    # training", in the eval of synth_v4)
    if len(fits) < MAYBE_WHEN and len(readable) < MAYBE_READABLE:
        # few posts name the topic in its own words ("lazy weeknight meals"): the search's next best are read too, and one
        # counts only when the model lists it as about the topic (check_points' need_about)
        maybe = [it for it in maybes if len(own_text_lines(it, extra)) >= MIN_TEXT][:max(0, MAYBE_READS - len(readable))]
        steps["maybe_reads"] = len(maybe)
    readable = readable + maybe
    facts, info = details_many(readable, ["key_points"], view.lib, store=bot.store, person=h, extra=extra, now=now,
                               context={"request": req["topic"]})
    cost += info["cost"]
    steps["reads"], steps["read_calls"] = len(readable), info["calls"]
    points_of = {it.id: (facts.get(it.id) or {}).get("key_points") or [] for it in readable}
    said = [it for it in readable if points_of[it.id]]
    read_ids = {it.id for it in readable}
    unread = [it for it in fits if it.id not in read_ids and len(own_text_lines(it, extra)) >= MIN_TEXT]
    out = {"topic": req["topic"], "points": [], "dropped": {}, "cited": [], "fits": fits, "said": said,
           "silent": [it for it in fits if it.id not in {x.id for x in unread} and not points_of.get(it.id)],
           "unread": unread, "extra": extra}
    steps["unread"] = len(unread)
    raw = {}
    if len(said) >= 1:
        try:
            raw, c = call(req["topic"], said, points_of, person=h)
            cost += c
            steps["synth_calls"] = 1
        except Exception as e:  # noqa: BLE001 - a failed call: the list of what fits, with no summary
            if llm.budget_stop(e):
                raise
            raw = {}
            steps["synth_error"] = type(e).__name__
        notes = []
        points, dropped = check_points(raw, said, extra, notes=notes, need_about={it.id for it in maybe},
                                       topic=req["topic"])
        points = spread(points, dropped, notes)   # round 11 fix, B (S2): at most 2 points from one item alone
        out["points"], out["dropped"], out["dropped_text"] = points, dropped, notes
        steps["points_model"] = len(raw.get("points") or []) if isinstance(raw, dict) and isinstance(
            raw.get("points"), list) else 0
    if maybe:   # a search-ranked item counts as fitting only when the model said it is about the topic
        about = raw.get("about") if isinstance(raw, dict) and isinstance(raw.get("about"), list) else []
        on = {said[n - 1].id for n in about if isinstance(n, int) and 1 <= n <= len(said)}
        gone = {it.id for it in maybe if it.id not in on}
        out["fits"] = fits + [it for it in maybe if it.id in on]
        out["said"] = [it for it in out["said"] if it.id not in gone]
        steps["maybe_fit"] = len(maybe) - len(gone)
    if len(out["points"]) < MIN_POINTS:
        out["thin"] = True
    order = []
    for p in out["points"]:
        for iid in p["ids"]:
            if iid not in order:
                order.append(iid)
    out["cited"] = [view.get(i) for i in order]
    # ---------- round 11 fix, B (S1, S2, S3): what the reply names, numbered as the person sees it ----------
    if out.get("thin"):   # the best 3: the one cited first, then the search's order
        listed = [it for it in out["cited"] if it is not None]
        listed += [it for it in out["fits"] if it.id not in {x.id for x in listed}]
        out["listed"] = listed[:THIN_LIST]
    named = [it for it in out["cited"] if it is not None] if not out.get("thin") else []
    out["lead"] = lead_words(req.get("how") or "any", named or out["fits"])
    out["how"] = req.get("how") or "any"
    out["thing"], out["context"] = focus(req["topic"])
    # ---------- end round 11 fix, B ----------
    steps["points"] = len(out["points"])
    steps["cited"] = len(order)
    steps["seconds"] = round(time.time() - t0, 2)
    out["steps"], out["cost"] = steps, cost
    return out


def synth_reads(bot, person, text, now):
    """Round 11, slice M: the read before the interpreter. None when the message is not such a request (or the answer
    is not in English, or the feature is off)."""
    if not ON or bot._answer_lang():
        return None
    from zoneinfo import ZoneInfo
    today = now.astimezone(ZoneInfo(person.get("timezone") or "UTC")).date()
    req = read(text, today)
    if req is None:
        req = read_ask_mine(text)   # round 11 fix, B (V1): "ask my videos about X", only with MVP_VIDEO_ASK=1
    if req is None:
        return None
    h = person["handle"]
    last = bot.store.last_answer(h)
    if req["these"] and not (last and last.get("items")):
        return None
    if req["these"] and not req["topic"]:
        goal = last.get("goal") or (bot.store.get_state(f"lastspec:{h}") or {}).get("text") or ""
        if goal.startswith("history:"):   # the merge of round 11: after a history answer, its topic or channel
            from . import history
            st = bot.store.get_state(history.STATE.format(h=h)) or {}
            q = (st.get("q") or {}) if st.get("run_id") == last.get("run_id") else {}
            goal = " ".join(q.get("topic") or []) or q.get("channel") or ""
        req = dict(req, topic=" ".join(goal.split())[:80] or "these")
    if req.get("window") is not None:
        ref = _window(bot, person, req, today, now)
        if not isinstance(ref, dict):
            return ref
        req = ref
    req = _limit(bot, person, req)   # round 11 fix, B (S2): "from what i watched" reads only what was watched
    return run(bot, person, req, now, last=last)


# ---------- the merge of round 11 (DESIGN 18, seam b): the window's items, from slice H's record ----------
VERB = {"watched": "watched", "liked": "liked", "saved": "saved", "any": "watched or saved"}


def _window(bot, person, req, today, now=None):
    """The request with the window's items (`only`, `dates`) and its words, or a reply's reference when the window
    lies wholly outside the record (said plainly, with where the export ends or starts; no model call)."""
    from . import history as Hs
    h = person["handle"]
    view = bot.view(person["library"])
    rec = Hs.record(view, person.get("timezone") or "UTC")
    how = req.get("how") or "any"
    kinds = set(Hs.HOW_KINDS[how])
    plats = sorted({p for (p, k) in rec.starts if k in kinds})
    if req.get("platforms"):
        plats = [p for p in plats if p in req["platforms"]] or list(req["platforms"])
    w = req["window"]
    start, end = Hs.resolve(w, rec, plats, today)
    newest = max((rec.ends[p] for p in plats if p in rec.ends), default=None)
    q = Hs.HistoryQuery(kind="count", how=how)
    oldest = Hs._record_start(rec, plats, q)
    said = Hs.window_noun(w, start, end)
    if newest and start and start > newest:
        bot.note(intent="synth")
        el = Hs.ends_line(rec, plats)
        return bot.send(h, f"I can't see {said}: {el[:1].lower() + el[1:]} {Hs.REFRESH['en']}")
    if oldest and end and end < oldest:
        bot.note(intent="synth")
        sl = Hs.start_line(rec, plats, q)
        return bot.send(h, f"I can't see {said}: {sl[:1].lower() + sl[1:]}")
    dates = {}
    for iid, evs in rec.events.items():
        it = view.items.get(iid)
        if it is None or it.platform not in plats:
            continue
        ds = [d for d, k in evs if k in kinds and (start is None or d >= start) and (end is None or d <= end)]
        if ds:
            dates[iid] = max(ds).isoformat()
    tail, said = [], []
    if newest is not None and (end is None or end >= newest):
        # the merge of round 11's fixes (seam d, R4): where the export ends always stays (it changes the answer); the
        # hint on sending a new export is said once in a stretch of 6 hours, shared with the history answers
        tail = [Hs.ends_line(rec, plats)]
        if now is None or not ({"range", "refresh"} & Hs.said_lately(bot, h, now)):
            tail.append(Hs.REFRESH["en"])
            said.append("refresh")
    return dict(req, only=set(dates), dates=dates, platforms=req.get("platforms") or [],
                when=Hs.window_words(w, start, end, cap=False).rstrip(","), verb=VERB[how],
                window_tail=" ".join(x for x in tail if x), said=said)
# ---------- end the merge of round 11 ----------


def run(bot, person, req, now, last=None):
    from . import texts as T
    from .store import now_iso
    h = person["handle"]
    bot.note(intent="synth")
    status, err, res, stopped = "ok", None, None, False
    t0 = time.time()
    try:
        res = summarize(bot, person, req, now, last=last)
    except Exception as e:  # noqa: BLE001 - one failed run never stops the bot
        status, err = "error", type(e).__name__
        stopped = llm.budget_stop(e)
    shown = (res or {}).get("cited") or []
    if res and (not res["points"]):
        shown = res["fits"][:5]
    if res and res.get("thin"):   # round 11 fix, B (S3): the numbered list the reply shows, in its order
        shown = res.get("listed") or shown
    run_id = bot.store.add_run(handle=h, kind="synth", at=now_iso(now), n_candidates=(res or {}).get("steps", {}).get(
        "candidates", 0), n_picks=len(shown), n_dropped=sum(((res or {}).get("dropped") or {}).values()),
        cost_usd=round((res or {}).get("cost", 0.0), 6), status="error" if status == "error" else (
            "picked" if shown else "none"), error=err, prompt_version=PROMPT_VERSION, seconds=round(time.time() - t0, 2),
        dropped=(res or {}).get("dropped") or {}, steps=(res or {}).get("steps") or {})
    bot.note(run_id=run_id)
    if status == "error":
        return bot.send(h, T.LIMIT_TOTAL if stopped else T.RUN_ERROR)
    if res is not None and req.get("when"):   # the merge of round 11: the window said back, and where the record ends
        res.update(when=req["when"], verb=req["verb"], window_tail=req.get("window_tail") or "")
    msg = T.synth_message(res, video_offer=_video_offer(shown, thin=bool(res and res.get("thin"))))
    if req.get("said"):   # the merge of round 11's fixes (seam d): the notes said, once in a stretch (R4)
        from . import history as Hs
        Hs.note_said(bot, h, now, req["said"])
    if shown:
        # round 11 fix, B (V1): "ask them" right after reads this answer's YouTube videos and its topic
        from . import videoask
        if videoask.on():
            bot.store.set_state(f"videomany:{h}", {"run_id": run_id, "topic": req["topic"][:120],
                                                    "at": now.isoformat()})
        from .compose import display_title
        for i, it in enumerate(shown, 1):
            bot.store.add_delivery(h, None, run_id, it.id, i, at=now)
        bot.store.set_last_answer(h, run_id, None, [it.id for it in shown], req["topic"])
        lines_of = {}
        for p in res["points"]:
            for iid in p["ids"]:
                lines_of.setdefault(iid, []).append(p["text"])
        recs = [{"item_id": it.id, "title": display_title(it), "url": it.url, "platform": it.platform,
                 "video_id": getattr(it, "video_id", None), "creator": it.creator, "facts": {},
                 "lines": [], "line_kinds": None, "main": True, "points": lines_of.get(it.id, [])} for it in shown]
        bot._keep_answer(run_id, h, None, req["topic"], "picks", msg, recs)
        # "another" after a summary: one more on the same topic, without the items it cited
        spec = _spec(req["topic"], req.get("platforms") or [], req.get("kinds") or [])
        bot.store.set_state(f"lastspec:{h}", {"spec": spec.stored(), "rule_id": None, "text": req["topic"][:300],
                                              "shown": [it.id for it in shown], "clear_shown": 0})
    return bot.send(h, msg, run_id)


# ---------- the merge of round 11 (DESIGN 18, seam c): slice Q's offer, only with MVP_VIDEO_ASK=1 and a YouTube video
def _video_offer(shown, thin=False):
    """The words that offer to ask a cited video itself, by its number in this answer's sources (as "ask video N"
    reads it), or "" when the setting is off or no shown item is a YouTube video. Round 11 fix, B (S1, V1): only the
    YouTube sources are offered, by the numbers the person sees; two or more also get "ask them"."""
    from . import texts as T
    from . import videoask
    if not videoask.on():
        return ""
    yt = [n for n, it in enumerate(shown, 1) if videoask.video_id(it)]
    if not yt:
        return ""
    return T.synth_video_offer(yt, total=len(shown), thin=thin)
# ---------- end the merge of round 11 ----------
