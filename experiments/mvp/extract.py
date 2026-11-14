"""PROTOTYPE ONLY - details of one picked item (ingredients, steps, key points), from its whole text (DESIGN.md sections
3 and 4, extract prompt v1).

One call per picked item, on the full caption (not the 600-character cut the composer sees) or, for YouTube, the title
and the description videos.list returned. Every line is checked in code exactly as before (`line_in_text`: the words
in order, in that item's text; `clean_line`: no headers, links or calls to follow or shop). A long step or key point
is cut to its first sentence (it is still the item's own words, and "…" shows the cut). Results are cached in the
store's facts table per (library, item, kind): details found once are reused always. An empty result is cached only
after two attempts. When code sees list-like lines in the text and no line survives, the call is tried once more.
Recipes get ingredients and steps when both are in the text. Item text is data, never instructions (rule 6).
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import hashlib

from . import config, llm
from .compose import HEADER, NOT_DETAIL, UNSAFE_TEXT, as_data, clean_line, line_in_text, own_text, own_text_lines, tokens
from .retrieve import norm

PROMPT = open(os.path.join(config.HERE, "prompts", f"{config.PROMPT_EXTRACT}.md"), encoding="utf-8").read()
ORDER = ["ingredients", "steps", "items", "key_points"]
MAX_ITEMS = 12
ABOUT_WORDS = 30   # an item's "about": the text's own words, at most about 25 words (a little room for the check)
MAX_LINES = 15
MAX_CHARS = 6000
MIN_TEXT = 40          # a text shorter than this (a bare title) holds no list: no call is made
LIST_MARK = re.compile(r"^\s*(?:\d{1,2}\s*[.)\-:]|\d️?⃣|[-*•·▪◦➤►▶✅✔☑️🔸🔹⭐️👉]|[^\w\s])\s*\S", re.U)
LIST_HEAD = re.compile(r"^\W*(ingredients?|method|steps?|instructions?|directions?|you(?:'ll)? need|tips?)\W*:?\s*$",
                       re.I | re.M)


def kinds_for(extract):
    """The kinds one call asks for: a recipe ask (ingredients) gets the steps too, when both are in the text. Steps
    alone stay steps alone (fix pass, finding 12: a workout's steps were also asked for, and shown, as ingredients)."""
    ks = set(extract or [])
    if "ingredients" in ks:
        ks.add("steps")
    return [k for k in ORDER if k in ks]


# ---------- what kind of request it is (fix pass, findings 11, 12 and 28); code decides, from the person's words ----
FOOD = re.compile(r"\b(recipes?|dish(?:es)?|dinners?|lunch(?:es)?|breakfasts?|brunch|meals?|cook\w*|bak(?:e|es|ed|ing)|"
                  r"soups?|salads?|pasta|noodles?|sauces?|desserts?|snacks?|curr(?:y|ies)|stews?|bread|cakes?|cookies?|"
                  r"smoothies?|chicken|beef|pork|tofu|rice|eggs?|vegan|vegetarian|ingredients?|food)\b", re.I)
FITNESS = re.compile(r"\b(workouts?|exercises?|stretch\w*|yoga|pilates|hiit|warm-?ups?|abs|mobility|"
                     r"cardio|gym|lifting|squats?|push-?ups?|fitness|routines?)\b", re.I)
HOWTO = re.compile(r"\b(tutorials?|how[- ]to|how do i|guides?|lessons?|walk-?through|step[- ]by[- ]step|courses?|"
                   r"projects?|build|make|model(?:ing|ling)?|draw\w*|paint\w*|knit\w*|sew\w*|crochet\w*)\b", re.I)


def topic_kind(*texts):
    """'food', 'fitness', 'making' or None, from the request's own words (goal, searches, the message)."""
    t = " ".join(x for x in texts if x)
    if FITNESS.search(t) and not re.search(r"\b(recipes?|ingredients?|dish(?:es)?|meals?)\b", t, re.I):
        return "fitness"
    if FOOD.search(t):
        return "food"
    if HOWTO.search(t):
        return "making"
    return None


def fit_extract(extract, *texts):
    """The details asked for, as code keeps them: never ingredients for a workout (checker, finding 12: a form that
    asked for "ingredients" for a leg workout showed its exercises under "Ingredients")."""
    out = list(extract or [])
    if "ingredients" in out and topic_kind(*texts) == "fitness":
        out = [k for k in out if k != "ingredients"] or ["steps"]
    return out


# fix pass 3, finding 71: default details are for recipes, workouts and make-or-build tutorials only. A "how to" or a
# guide about something nobody makes ("how to start investing") gets none, and key points come only when asked for.
MAKING = re.compile(r"\b(tutorials?|build\w*|make|making|model(?:ing|ling)?|draw\w*|paint\w*|knit\w*|sew\w*|"
                    r"crochet\w*|craft\w*|diy|sculpt\w*|woodwork\w*|carv\w*|pottery|origami|render\w*)\b", re.I)
# a pick that is a talk, a list of habits or an opinion gets no default Steps, whatever the request
TALK = re.compile(r"\b(talks?|ted|tedx|podcasts?|interviews?|keynote|lecture|speech|opinions?|my thoughts|reaction|"
                  r"commentary|rant|habits?|mindset|reasons?|lessons? (?:i|we)(?:'ve)? learned|things i wish|"
                  r"rules (?:for|of)|secrets? (?:of|to))\b", re.I)


ITEMS_DEFAULT = ["items", "key_points"]


def default_extract(spec, *texts):
    """The details a recommended pick gets when the person did not name any (finding 28): a recipe its ingredients
    and steps, a workout its steps (shown as exercises), a make-or-build tutorial its steps. Round 7, finding 90: every
    other request gets the named things its top picks list ("items"), then their key points (the gist)."""
    c = spec.content
    if c.extract or c.source not in ("library", "recent"):
        return list(c.extract)
    words = [c.goal or "", *c.searches, *texts]
    kind = topic_kind(*words)
    if kind == "making" and not MAKING.search(" ".join(x for x in words if x)):
        return list(ITEMS_DEFAULT)
    return {"food": ["ingredients", "steps"], "fitness": ["steps"], "making": ["steps"]}.get(kind, list(ITEMS_DEFAULT))


def items_default(extract, asked):
    """True when the details are the default items and key points (nobody asked for a kind)."""
    return not asked and list(extract or []) == ITEMS_DEFAULT


# round 7, finding 90: a request that asks for things (libraries, tools, opportunities ...): when its picks' text holds
# none, the answer says the details are in the post's slides or video
THINGS = re.compile(r"\b(librar(?:y|ies)|tools?|resources?|opportunit\w*|programs?|programmes?|places?|spots?|books?|apps?|"
                    r"products?|ideas?|tips?|websites?|sites?|courses?|internships?|scholarships?|fellowships?|grants?|"
                    r"events?|restaurants?|cafes?|bars?|shops?|stores?|brands?|recommendations?|frameworks?|plugins?|"
                    r"extensions?|templates?|fonts?|icons?|design systems?|kits?|channels?|podcasts?|newsletters?|"
                    r"deadlines?|jobs?|hackathons?|competitions?|awards?|what do i know about|which \w+ should)\b", re.I)


def asks_for_things(*texts):
    return bool(THINGS.search(" ".join(t for t in texts if t)))


# checker, finding 71: a caption that writes out a recipe, a workout or its steps is not a talk, whatever else it says
# ("let's talk about this pasta", "one of the reasons I love it")
WRITTEN_OUT = re.compile(r"\b(?:ingredients?|instructions|method|directions|steps?)\s*:|"
                         r"\b\d+(?:[./]\d+)?\s*(?:g|kg|ml|l|oz|lbs?|tbsp|tsp|cups?|tablespoons?|teaspoons?)\b|"
                         r"\b\d+\s*(?:reps|sets|rounds)\b|\b\d+\s*x\s*\d+\b", re.I)


def default_fits(text):
    """Fix pass 3, finding 71: whether a pick's own text may get the default details (not a talk, a list of habits
    or an opinion piece, unless it writes out a recipe, a workout or its steps)."""
    return not TALK.search(text or "") or bool(WRITTEN_OUT.search(text or ""))


def list_like(text):
    """True when the text looks like it holds a list: a list heading, or 3 or more lines that start with a list mark."""
    if LIST_HEAD.search(text or ""):
        return True
    return sum(1 for line in (text or "").splitlines() if LIST_MARK.match(line)) >= 3


STEP_LIMIT = 260


def _cut(line, limit=105):
    """A long line cut to its first sentence, or to a word boundary, with '…'. Still the item's own words."""
    if len(line) <= limit:
        return line
    first = re.split(r"(?<=[.!?])\s", line, maxsplit=1)[0]
    if 15 <= len(first) <= limit:
        return first
    return line[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"


def verify(raw_lines, text, kind):
    """(lines, dropped): the model's lines that are in the text, cleaned; at most MAX_LINES."""
    out, dropped = [], 0
    if isinstance(raw_lines, str):   # one line given as a string, not a list: read as that one line
        raw_lines = [raw_lines]
    if not isinstance(raw_lines, list):
        raw_lines = []
    for raw in raw_lines[:MAX_LINES + 5]:
        line = " ".join(str(raw).split())[:400]
        if not line:
            continue
        if not line_in_text(line, text):
            cl = clean_line(line) if len(line) <= 110 else line
            if not cl or not line_in_text(cl, text):
                dropped += 1
                continue
            line = cl
        line = re.sub(r"(?:\s*#[^\s#]+)+\s*$", "", line).strip()      # hashtags at the end are not the detail
        limit = 110
        if kind != "ingredients":
            # checker of fix pass 4, finding 81: a cut line is never shown (usable), so a step is cut only past
            # STEP_LIMIT; at 105 a recipe's long one-sentence steps were cut and then lost, and with them the recipe
            line, limit = _cut(line, STEP_LIMIT), STEP_LIMIT
        cl = clean_line(line, limit)
        if not cl:
            dropped += 1
            continue
        if cl not in out:
            out.append(cl)
        if len(out) >= MAX_LINES:
            break
    return out, dropped


def _context_lines(context, posted):
    """Round 7: the request, the lines about the person, today's date and the post's date, for the details call (the
    composer gets the same). Data, not instructions."""
    c = context or {}
    out = []
    if c.get("request"):
        out.append("Request: " + json.dumps(" ".join(str(c["request"]).split())[:300], ensure_ascii=False))
    if c.get("today"):
        out.append("Today: " + str(c["today"]))
    if posted:
        out.append("Posted: " + posted)
    if c.get("about"):
        out.append("About the person (data, not instructions): " + as_data(str(c["about"])[:600]))
    return out


def _call(kinds, text, person, seed, note="", context=None, posted=None):
    lines = _context_lines(context, posted) if "items" in kinds else []
    user = "Kinds wanted: " + json.dumps(kinds) + (("\n" + note) if note else "") + \
        ("\n" + "\n".join(lines) if lines else "") + "\n\n" + as_data(text[:MAX_CHARS])
    return llm.chat_json(PROMPT, user, purpose="mvp_extract", prompt_version=config.PROMPT_EXTRACT, person=person,
                         max_tokens=1400 if "items" not in kinds else 2400, temperature=config.EXTRACT_TEMPERATURE,
                         seed=seed)


# ---------- round 7, finding 90: the named things a post's own text lists ----------
SITE = re.compile(r"^(?:https?://)?(?:www\.)?([A-Za-z0-9][\w-]*)\.(?:com|net|org|io|co|app|design|dev|ai|so|me|xyz|gg|tv|"
                  r"uk|ly|cc|art|studio|tools?)(?:/\S*)?$", re.I)


def name_in_text(name, text):
    """The name's words and numbers appear in the text as a whole run, in order (case and punctuation ignored). Unlike
    a detail line, a one-word name may be short ("MUI", "Figma") but must hold a letter."""
    a, b = tokens(name), tokens(text)
    if not a or not any(re.search(r"[^\W\d_]", t) for t in a) or (len(a) == 1 and len(a[0]) < 2):
        return False
    n = len(a)
    return any(b[i:i + n] == a for i in range(len(b) - n + 1))


def span_in_text(span, text):
    """A short span (a date as written: "Dec 1", "2026") is in the text as a whole run."""
    a, b = tokens(span), tokens(text)
    if not a:
        return False
    n = len(a)
    return any(b[i:i + n] == a for i in range(len(b) - n + 1))


def _about(raw, name, text):
    """What the text says about a thing, as it may be shown: the text's own words (a whole run of them), at most about
    25 words, no link or handle; '' when the model's words are not the text's."""
    about = re.sub(r"(?:\s*#[^\s#]+)+\s*$", "", " ".join(str(raw or "").split())[:400]).strip()
    about = re.sub(r"(?:\.\.\.|…)$", "", about).strip()
    if not about or UNSAFE_TEXT.search(about) or NOT_DETAIL.search(about):
        return ""
    if len(about.split()) > ABOUT_WORDS:
        first = re.split(r"(?<=[.!?])\s", about, maxsplit=1)[0]
        if len(first.split()) > ABOUT_WORDS:
            return ""
        about = first
    if not line_in_text(about, text):
        cl = clean_line(about, 260)
        if not cl or not line_in_text(cl, text):
            return ""
        about = cl
    if norm(about).strip(" .:") == norm(name).strip(" .:"):
        return ""
    return about


def verify_items(raw, text):
    """(items, dropped): the model's items whose name is in the text, each {name, about, when, fit}. An item never
    loses its name; its about and when are kept only when they are the text's own words. fit "no" (the text shows it
    does not fit the request) is left out; "yes" before "unknown"."""
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return [], 0
    out, dropped, seen = [], 0, set()
    for r in raw[:MAX_ITEMS + 8]:
        if not isinstance(r, dict):
            dropped += 1
            continue
        name = " ".join(str(r.get("name") or "").split()).strip(" -:•*·\"'")
        m = SITE.match(name)
        if m:   # a site named by its address: its name alone (PRIV-9: no web address is one of our details)
            name = m.group(1)
        if not name or len(name) > 60 or "#" in name or "@" in name or UNSAFE_TEXT.search(name) \
                or NOT_DETAIL.search(name) or HEADER.match(name) or not name_in_text(name, text):
            dropped += 1
            continue
        key = norm(name)
        if key in seen:
            continue
        fit = str(r.get("fit") or "unknown").strip().lower()
        if fit == "no":
            dropped += 1
            continue
        seen.add(key)
        when = " ".join(str(r.get("when") or "").split())[:60]
        if when and (not span_in_text(when, text) or UNSAFE_TEXT.search(when)):
            when = ""
        out.append({"name": name, "about": _about(r.get("about"), name, text), "when": when,
                    "fit": "yes" if fit == "yes" else "unknown"})
    out = [x for x in out if x["fit"] == "yes"] + [x for x in out if x["fit"] != "yes"]
    return out[:MAX_ITEMS], dropped


def items_cache_kind(context):
    """The facts table's kind for one request's items: the items that answer a request depend on the request and the
    person (round 7), so they are cached per request, not per post alone."""
    c = context or {}
    key = json.dumps([c.get("request") or "", c.get("about") or ""], ensure_ascii=False)
    return "items:" + hashlib.sha256(key.encode()).hexdigest()[:16]


# fix pass 4, finding 81: a line that only says what the video is ("This tutorial teaches how to ...", "In this video
# ...") is not a step, and one line is not steps
DESCRIBES = re.compile(r"^\W*(?:in\s+)?(?:this|today'?s)\s+(?:\w+\s+){0,3}?(?:video|tutorial|class|course|lesson|episode|"
                       r"guide|series|vlog)s?\b|^\W*(?:in\s+this|today\s+(?:i|we)|welcome)\b"
                       r"|^\W*(?:learn|discover)\s+how\b|^\W*(?:i|we)(?:'ll|\s+will|'m\s+going\s+to|\s+am\s+going\s+to)\s+"
                       r"(?:show|teach|walk)\b", re.I)
MIN_STEPS = 2


def usable(facts):
    """The details as they may be shown: never a line cut off with "…" (finding 81), never a sentence about the video
    under Steps, and steps only when at least two lines are left. Cached lines are read through this too, so a store
    made before keeps working."""
    out = dict(facts or {})
    for k in ("steps", "key_points"):
        if k not in out:
            continue
        lines = [x for x in out[k] or [] if not str(x).rstrip().endswith(("…", "..."))]
        if k == "steps":
            lines = [x for x in lines if not DESCRIBES.search(str(x))]
            if len(lines) < MIN_STEPS:
                lines = []
        out[k] = lines
    return out


def details(it, extract, library, store=None, person=None, extra=None, now=None, context=None):
    """({kind: lines}, info) for one item, as they may be shown (usable). context: the request, the lines about the
    person and today's date, for the items kind (round 7)."""
    facts, info = _details(it, extract, library, store=store, person=person, extra=extra, now=now, context=context)
    return usable(facts), info


def _details(it, extract, library, store=None, person=None, extra=None, now=None, context=None):
    """({kind: lines}, info) for one item. info: cost, calls, dropped, cached (kinds read from the cache), errors. On a
    failed call the kinds not read are left out (nothing is cached, and nothing is said about them). "items" are
    objects ({name, about, when, fit}), cached per request (items_cache_kind)."""
    from .dates import posted_on
    kinds = kinds_for(extract)
    info = {"cost": 0.0, "calls": 0, "dropped": 0, "cached": 0, "errors": 0}
    if not kinds:
        return {}, info
    now = now or datetime.now(timezone.utc)
    context = dict(context or {}, today=(context or {}).get("today") or now.date().isoformat())
    names = {k: (items_cache_kind(context) if k == "items" else k) for k in kinds}
    since = (now - timedelta(days=config.YOUTUBE_KEEP_DAYS)).astimezone(timezone.utc).isoformat(timespec="seconds")
    source = "youtube_api" if ((extra or {}).get(it.id) or {}).get("description") else "caption"
    # with a YouTube description now in hand, an empty result read from the title alone does not count
    got_rows = (store.facts_get(library, it.id, [names[k] for k in kinds], since=since,
                                empty_source=source if source == "youtube_api" else None) if store is not None else {})
    have = {k: got_rows[names[k]] for k in kinds if names[k] in got_rows}
    info["cached"] = len(have)
    need = [k for k in kinds if k not in have]
    if not need:
        return {k: have[k] for k in kinds}, info
    full = own_text_lines(it, extra)
    if len(full) < MIN_TEXT:   # a bare title: no list to read, and nothing worth caching
        return {**{k: [] for k in need}, **have}, info
    text = own_text(it, extra)
    got, tries = {k: [] for k in need}, {k: 0 for k in need}
    ask, note = list(need), ""
    posted = posted_on(it, extra)
    for attempt in range(2):
        try:
            raw, cost = _call(ask, full, person, config.EXTRACT_SEED + attempt, note, context=context, posted=posted)
        except Exception:  # noqa: BLE001 - a failed details call never fails the answer
            info["errors"] += 1
            if attempt == 0:
                return dict(have), info
            break
        info["cost"] += cost
        info["calls"] += 1
        returned_any = False
        for k in ask:
            tries[k] += 1
            got_raw = raw.get(k) if isinstance(raw, dict) else None
            lines, dropped = verify_items(got_raw, text) if k == "items" else verify(got_raw, text, k)
            info["dropped"] += dropped
            returned_any = returned_any or bool(dropped)
            got[k] = lines
        ask = [k for k in ask if not got[k]]
        if got.get("items"):   # round 7: the named things were read; their key points are not worth a second call
            ask = [k for k in ask if k != "key_points"]
        if not ask or not list_like(full):   # retry only when the text looks like it holds a list
            break
        note = ("Your last lines were not exact copies of the text. Copy the words exactly as written."
                if returned_any else "Look again: the text seems to hold a list.")
    if store is not None:
        for k in need:
            prev = store.facts_attempts(library, it.id, names[k], source=source)
            store.facts_put(library, it.id, names[k], got[k], config.PROMPT_EXTRACT,
                            attempts=1 if got[k] else prev + tries[k], source=source, at=now)
    return {k: (have.get(k) if k in have else got[k]) for k in kinds}, info


def details_many(items, extract, library, store=None, person=None, extra=None, now=None, workers=4, context=None):
    """details() for several picked items at once (the calls run in parallel). Returns ({item_id: {kind: lines}},
    info summed)."""
    total = {"cost": 0.0, "calls": 0, "dropped": 0, "cached": 0, "errors": 0}
    if not items or not kinds_for(extract):
        return {}, total
    if len(items) == 1:
        res = [details(items[0], extract, library, store, person, extra, now, context)]
    else:
        with ThreadPoolExecutor(max_workers=min(workers, len(items))) as ex:
            res = list(ex.map(lambda it: details(it, extract, library, store, person, extra, now, context), items))
    out = {}
    for it, (facts, info) in zip(items, res):
        out[it.id] = facts
        for k in total:
            total[k] += info[k]
    return out, total
