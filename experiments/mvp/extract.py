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
    for x in out:   # checker, round 7: an item's words must be about that item, never another one's
        if x["about"] and not about_belongs(x["name"], x["about"], [y["name"] for y in out if y is not x], text):
            x["about"] = ""
    out = [x for x in out if x["fit"] == "yes"] + [x for x in out if x["fit"] != "yes"]
    return out[:MAX_ITEMS], dropped


ABOUT_REACH = 60   # tokens: an item's words start at most this far after its name


def _runs(a, b):
    """Start indices of the token run `a` in the tokens `b`."""
    n = len(a)
    return [i for i in range(len(b) - n + 1) if n and b[i:i + n] == a]


def about_belongs(name, about, others, text):
    """Checker, round 7 (rule 1: "never put a sentence about one thing under another thing's name"): the words shown
    for a thing are about that thing. They name no other listed thing (a whole one-line list is not about each of its
    things), and they hold its name or start after it in the text, with no other listed thing named in between."""
    a, na, b = tokens(about), tokens(name), tokens(text)
    other = [t for t in (tokens(o) for o in others) if t and t != na and not _runs(t, na)]
    if any(_runs(t, a) for t in other):
        return False
    if _runs(na, a):
        return True
    starts, names = _runs(a, b), _runs(na, b)
    marks = sorted(i for t in other for i in _runs(t, b))
    for s in starts:
        for n0 in names:
            if n0 + len(na) <= s <= n0 + len(na) + ABOUT_REACH and not any(n0 < m < s for m in marks):
                return True
    return False


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


def details(it, extract, library, store=None, person=None, extra=None, now=None, context=None, once=False):
    """({kind: lines}, info) for one item, as they may be shown (usable). context: the request, the lines about the
    person and today's date, for the items kind (round 7). Round 8, finding 93: the items as they may be shown
    (clean_items), also when they were read from the cache of an earlier prompt."""
    facts, info = _details(it, extract, library, store=store, person=person, extra=extra, now=now, context=context,
                           once=once)
    facts = usable(facts)
    if facts.get("items"):
        facts["items"], n = clean_items(facts["items"], it, extra, facts.get("key_points"))
        if n:
            info["junk_items"] = info.get("junk_items", 0) + n
    return facts, info


# ---------- round 8, finding 93: what an item is (a specific named thing), enforced where code can ----------
# a determiner or an adjective before a name that makes it a common noun ("a list of the some best design systems")
DETERMINERS = set("""a an the some any best right top these those this that your my our their every each such many
most good great new other perfect ultimate essential favorite favourite cool useful amazing""".split())
# words that never make a name on their own: kinds of thing, audiences, counts and the words around them
GENERIC = set("""tool tools library libraries resource resources site sites website websites app apps program programs
programme programmes opportunity opportunities internship internships scholarship scholarships fellowship fellowships
grant grants event events course courses class classes book books template templates kit kits framework frameworks
platform platforms system systems design designs ui ux component components font fonts icon icons idea ideas tip tips
project projects list lists thing things stuff way ways place places spot spots restaurant restaurants cafe cafes recipe
recipes deadline deadlines application applications job jobs plugin plugins extension extensions channel channels podcast
podcasts newsletter newsletters product products brand brands shop shops store stores competition competitions hackathon
hackathons award awards summer winter spring fall autumn guide guides video videos post posts reel reels series part
student students underclassmen upperclassmen freshmen freshman sophomores sophomore juniors seniors beginners beginner
designers designer developers developer devs founders founder creators creator entrepreneurs everyone anyone women men
kids teens grads graduates people you free best top new great good cool useful amazing essential must have paid online
open source high quality cheap premium popular favorite favourite ultimate perfect awesome""".split())
NAME_STOP = set("""a an and the of for to in on with my your our this that is it at by from or as be are was were has have
its it's so if but not no all any some these those them they we you i me us very just more most much also too here there
one get got can will""".split())


def _occurrences(name, text):
    """(matched span, the word before it, the characters around it) for each place the name occurs in the text, its
    words in order (case, and punctuation between them, ignored)."""
    words = re.findall(r"[^\W_]+", name)
    if not words:
        return []
    pat = r"(?<![^\W_])" + r"[\W_]{1,3}".join(re.escape(w) for w in words) + r"(?![^\W_])"
    out = []
    for m in re.finditer(pat, text, re.I):
        before = re.findall(r"[^\W_']+", text[max(0, m.start() - 40):m.start()])
        out.append((m.group(0), before[-1].lower() if before else "",
                    text[max(0, m.start() - 1):m.start()], text[m.end():m.end() + 2]))
    return out


def _mostly_caps(text):
    letters = [ch for ch in text if ch.isalpha()]
    return bool(letters) and sum(ch.isupper() for ch in letters) >= 0.8 * len(letters)


def generic_name(name):
    """A name made only of kinds of thing, audiences, counts and small words ("design systems", "underclassmen", "5
    tools", "FREE PROGRAMS FOR STUDENTS"): never a specific thing."""
    ws = [w.lower() for w in re.findall(r"[^\W_]+", name)]
    return bool(ws) and all(w in GENERIC or w in NAME_STOP or w.isdigit() for w in ws)


def common_noun(name, text):
    """True when the name, everywhere it occurs, is used as a common noun: all lower case after a determiner or an
    adjective ("the best design systems"), or all lower case with no digit, dot, @ or capital anywhere it occurs; or
    ending in two lower-case kind words after one ("the right Figma design system"). Text in capitals throughout cannot
    use the capital test (the other tests still apply)."""
    occ = _occurrences(name, text)
    if not occ:
        return False
    caps = _mostly_caps(text)

    def common(span, prev, left, right):
        site = left == "@" or bool(re.match(r"\.[A-Za-z]", right))
        lower = not re.search(r"[A-Z\d.]", span) and not site
        if not caps and lower:
            return True
        tail = re.findall(r"[^\W_]+", span)[-2:]
        return prev in DETERMINERS and len(re.findall(r"[^\W_]+", span)) >= 3 and \
            all(w.islower() and w in GENERIC for w in tail)
    return all(common(*o) for o in occ)


def _content(words, skip=()):
    return [w for w in words if w not in NAME_STOP and w not in skip and not w.isdigit()]


def headline_of(it):
    """The post's headline: its first line, without a leading count or list mark."""
    line = re.sub(r"^[\W\d_]+", "", getattr(it, "first_line", "") or "")
    return line


def restates_headline(name, about, it):
    """The name is the post's headline (give or take case and a leading count) and its words say it again (a post
    about one thing may well open with its name: with no words of its own it is not this test's to drop)."""
    head = tokens(headline_of(it))
    na = [t for t in tokens(name) if not t.isdigit()]
    if not about or not head or not na or na != [t for t in head if not t.isdigit()][:len(na)] or len(na) < len(head) - 1:
        return False
    rest = _content(tokens(about or ""), skip=set(head))
    return len(rest) < 3


def own_line_words(name, about, text):
    """The words are the rest of the thing's own list line ("- Iconoir: free icons", "2. Lucide - clean icons")."""
    na, ab = tokens(name), tokens(about or "")
    for line in (text or "").splitlines():
        m = re.match(r"^\W*(?:\d{1,2}\s*[.)]\s*)?(.+?)\s*(?::|\s[-–—]\s)\s*(.+)$", line.strip())
        if m and tokens(m.group(1)) == na and tokens(m.group(2))[:len(ab)] == ab:
            return True
    return False


_MARK = re.compile(r"^\s*(?:\d{1,2}\s*[.)\-:]|\d️?⃣|[-*•·▪◦➤►▶→⇒➜➡✅✔☑🔸🔹⭐👉]|[^\w\s#@\"'(])\s*", re.U)


def list_entry(name, text):
    """Judgement, round 8 (live check of finding 93): the text lists the thing: a line of its own that starts with the
    name after a list mark (a number, a bullet, a dash, an emoji), or that is the name alone. A name the text only
    mentions in passing is not a list entry."""
    na = tokens(name)
    if not na:
        return False
    for line in (text or "").splitlines():
        m = _MARK.match(line)
        rest = line[m.end():] if m else line
        toks = tokens(rest)
        if toks == na or (m and toks[:len(na)] == na):
            return True
    return False


def thin_about(name, about, text=""):
    """The words add nothing to the name: fewer than 3 content words once the name's words are left out. (Judgement,
    round 8: the rest of the thing's own list line is its words when it holds one content word or more: "Iconoir:
    free icons" is a list's own description, "underclassmen: for underclassmen" is not.)"""
    n = len(_content(tokens(about or ""), skip=set(tokens(name))))
    return n < 3 and not (n >= 1 and own_line_words(name, about, text))


# "1 YC application. 0 startup experience. 4 hours before the deadline." is a story, not what the thing is
STORY = re.compile(r"(?:^|(?<=[.!?])\s+)\d+\s+(?:\S+\s+){0,5}?\S+[.!?]")


def story_about(about):
    return len(STORY.findall(about or "")) >= 2


def clean_items(items, it, extra=None, key_points=None):
    """(items, dropped): the items as they may be shown (round 8, finding 93). A name that is a kind of thing, an
    audience, a count, a common noun or the post's headline is dropped; words that add nothing to the name, or tell a
    story, are not words about it. A post about one thing (one item left, key points found) gives that thing its best
    one or two key points as its words. A post that names other things drops a thing with no words."""
    text = own_text_lines(it, extra)
    kept, dropped = [], 0
    for x in items or []:
        name, about = x.get("name") or "", x.get("about") or ""
        if generic_name(name) or common_noun(name, text) or restates_headline(name, about, it):
            dropped += 1
            continue
        x = dict(x)
        if about and (thin_about(name, about, text) or story_about(about)):
            x["about"] = ""
        kept.append(x)
    keys = [k for k in key_points or [] if k and not story_about(k)]
    if len(kept) == 1 and keys and not kept[0]["about"]:
        kept[0]["about"] = "; ".join(str(k).rstrip(" .;") for k in keys[:2])
        kept[0]["from_key_points"] = True
    if len(items or []) > 1:   # the post names other things: a thing with no words is not shown, unless the text
        # lists it on a line of its own (judgement, live check: a list of names is the concrete answer)
        n = len(kept)
        kept = [x for x in kept if x.get("about") or list_entry(x.get("name") or "", text)]
        for x in kept:
            if not x.get("about"):
                x["listed"] = True
        dropped += n - len(kept)
    return kept, dropped


# ---------- round 8, finding 94: does a post's text list named things? (a code score, on its own text) ----------
_BULLET = re.compile(r"^\s*(?:\d{1,2}\s*[.)\-:]|\d️?⃣|[-*•·▪◦➤►▶→⇒➜➡✅✔☑🔸🔹⭐👉]|[^\w\s#@])\s*\S", re.U)
_NAMED = re.compile(r"^\s*(?:\d{1,2}\s*[.)\-:]\s*)?\W*\s*([A-Z][\w.'&+-]*(?:\s+[A-Z0-9][\w.'&+-]*){0,3})\s*(?::|\s[-–—]\s)\s*\S")
_URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|net|org|io|co|app|design|dev|ai|so)\b", re.I)


def list_score(raw):
    """How much a text looks like it lists named things: lines that start with a number, a bullet, a dash, an emoji or
    an arrow; @handles; web addresses; "Name: words" or "Name - words" lines; capitalised names that start several
    lines. 0 for a text that lists nothing."""
    lines = [x for x in (raw or "").splitlines() if x.strip()]
    score = sum(1 for x in lines if _BULLET.match(x))
    score += len(re.findall(r"(?<![\w@])@[A-Za-z0-9_.]{2,}", raw or ""))
    score += len(_URL.findall(raw or ""))
    score += sum(1 for x in lines if _NAMED.match(x))
    firsts = [m.group(1) for m in (re.match(r"^\W*([A-Z][\w'-]+(?:\s+[A-Z][\w'-]+)?)", x) for x in lines[1:]) if m]
    score += max(0, len(set(firsts)) - 2) if len(firsts) >= 3 else 0
    return score


# finding 93, rule 5: a title or first line that promises a list ("5 free programs", "best design systems")
_KINDS = "|".join(sorted({w for w in GENERIC if w.endswith("s") and len(w) > 3}, key=len, reverse=True))
PROMISES = re.compile(rf"^\W*(?:\d+|three|four|five|six|seven|eight|nine|ten)\s+(?:[\w/-]+\s+){{0,3}}?(?:{_KINDS})\b|"
                      rf"\b(?:best|top)\s+(?:\d+\s+)?(?:[\w/-]+\s+){{0,3}}?(?:{_KINDS})\b|\b(?:a|my|the) list of\b",
                      re.I)


def promises_list(*lines):
    return any(PROMISES.search(x or "") for x in lines)


def _details(it, extract, library, store=None, person=None, extra=None, now=None, context=None, once=False):
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
        if not ask or not list_like(full) or once:   # retry only when the text looks like it holds a list (round 8:
            # never for a post read beyond the shown picks, finding 94)
            break
        note = ("Your last lines were not exact copies of the text. Copy the words exactly as written."
                if returned_any else "Look again: the text seems to hold a list.")
    if store is not None:
        for k in need:
            prev = store.facts_attempts(library, it.id, names[k], source=source)
            store.facts_put(library, it.id, names[k], got[k], config.PROMPT_EXTRACT,
                            attempts=1 if got[k] else prev + tries[k], source=source, at=now)
    return {k: (have.get(k) if k in have else got[k]) for k in kinds}, info


def details_many(items, extract, library, store=None, person=None, extra=None, now=None, workers=4, context=None,
                 once=()):
    """details() for several picked items at once (the calls run in parallel). Returns ({item_id: {kind: lines}},
    info summed). once: ids read with one call and no retry (round 8, finding 94)."""
    total = {"cost": 0.0, "calls": 0, "dropped": 0, "cached": 0, "errors": 0, "junk_items": 0}
    if not items or not kinds_for(extract):
        return {}, total
    once = set(once or ())
    if len(items) == 1:
        res = [details(items[0], extract, library, store, person, extra, now, context, once=items[0].id in once)]
    else:
        with ThreadPoolExecutor(max_workers=min(max(workers, 6), len(items))) as ex:
            res = list(ex.map(lambda it: details(it, extract, library, store, person, extra, now, context,
                                                 once=it.id in once), items))
    out = {}
    for it, (facts, info) in zip(items, res):
        out[it.id] = facts
        for k in total:
            total[k] += info.get(k, 0)
    return out, total
