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

PROMPT_VERSION = os.environ.get("MVP_SYNTH_PROMPT", "synth_v3")   # v3: v2 plus points spread over the items;
# v2: closer to the items' words, one idea per point, never what the items are (DESIGN 18.M); v1 and v2 stay as measured
PROMPT = open(os.path.join(config.HERE, "prompts", f"{PROMPT_VERSION}.md"), encoding="utf-8").read()
ON = os.environ.get("MVP_SYNTH", "1") != "0"    # off: the message goes to the interpreter as before (the eval's "before")
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


def read(text):
    """The request read from the message, or None: {"topic", "platforms", "kinds", "these"}. Code only; English only."""
    t = " ".join((text or "").split())
    if not t or len(t) > 220 or NOT_HERE.search(t):
        return None
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


def check_points(raw, items, extra=None, notes=None, need_about=()):
    """(points, dropped): the model's points that code can trace to the text of the items they cite.

    `items` is the numbered list the model saw (1-based). A point is kept only when it is a plain sentence (no link,
    handle or word about the bot or the item), at least one of its sources is a valid item number whose quote is that
    item's own words (3 words or more), its content words are found in the cited items' text (TRACE_MIN), every number
    in it is in that text, and it does not repeat a kept point. Each kept point: {"text", "ids", "share"}.
    `need_about`: ids of items that do not name the topic in their own words (search-ranked only): such an item counts
    as a source only when the model listed it in "about"."""
    from .compose import INTERNAL, UNSAFE_TEXT, check_text, numbers_backed, quote_ok, tokens
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
        ids, texts = [], []
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
        if not ids:
            drop("no_source", text)
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


# ---------- the call ----------
def _block(n, it, lines):
    from .compose import as_data, display_title
    body = "Title: " + display_title(it) + "\nPoints from its own text:\n" + "\n".join("- " + x for x in lines)
    return f"{n}. " + as_data(body)


def call(topic, items, points_of, person=None):
    """One model call over the numbered items. Returns (raw, cost)."""
    user = ("Topic: " + json.dumps(topic, ensure_ascii=False) + "\n\nItems:\n\n"
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
    cfb = captionmark.index(bot.store.caption_feedback(h))
    if req.get("these"):
        cands = [x for x in (view.get(i) for i in (last or {}).get("items") or []) if x is not None]
    else:
        ex_kinds, ex_platforms = bot._exclusions(h)
        spec = _spec(req["topic"], req.get("platforms") or [], req.get("kinds") or [])
        cands, meta = candidates(bot.pool, view, spec, disliked=bot.store.disliked(h), now=now, store=bot.store,
                                 exclude_kinds=ex_kinds, exclude_platforms=ex_platforms, k=CANDS, caption_fb=cfb)
        cost += meta.get("cost_usd", 0.0)
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
    if len(fits) < MAYBE_WHEN:
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
        points, dropped = check_points(raw, said, extra, notes=notes, need_about={it.id for it in maybe})
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
    req = read(text)
    if req is None:
        return None
    h = person["handle"]
    last = bot.store.last_answer(h)
    if req["these"] and not (last and last.get("items")):
        return None
    if req["these"] and not req["topic"]:
        goal = last.get("goal") or (bot.store.get_state(f"lastspec:{h}") or {}).get("text") or ""
        req = dict(req, topic=" ".join(goal.split())[:80] or "these")
    return run(bot, person, req, now, last=last)


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
    run_id = bot.store.add_run(handle=h, kind="synth", at=now_iso(now), n_candidates=(res or {}).get("steps", {}).get(
        "candidates", 0), n_picks=len(shown), n_dropped=sum(((res or {}).get("dropped") or {}).values()),
        cost_usd=round((res or {}).get("cost", 0.0), 6), status="error" if status == "error" else (
            "picked" if shown else "none"), error=err, prompt_version=PROMPT_VERSION, seconds=round(time.time() - t0, 2),
        dropped=(res or {}).get("dropped") or {}, steps=(res or {}).get("steps") or {})
    bot.note(run_id=run_id)
    if status == "error":
        return bot.send(h, T.LIMIT_TOTAL if stopped else T.RUN_ERROR)
    msg = T.synth_message(res, video_ask=os.environ.get("MVP_VIDEO_ASK") == "1")
    if shown:
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
