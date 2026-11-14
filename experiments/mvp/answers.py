"""PROTOTYPE ONLY - answers that answer, and answers that know today's date (round 7, findings 90 and 91; DESIGN.md
section 12). Pure functions over a checked composer result; the executor calls them.

- post_dates(): each shown pick's dates (posted, kept) and, for a time-sensitive request, its state from its own text
  (passed / old / open). A passed pick is never the lead or an alternative while anything not passed fits; an old one
  comes after everything fresher; among equal fits, newer first; a year in the request prefers posts that name it or
  were posted in the 12 months before it.
- choose_items(): the items answer, decided in code from what the details step read: 2 or more named things over the
  shown picks make the answer those things, each under the post it came from, with that post's link.
- stale reasons: a reason from a post older than 60 days never states a time-relative claim as current.
Nothing here is written by a model: names, abouts and dates are the post's own words, checked in extract.py, and every
date said to the person is worked out here.
"""
from datetime import date

from . import dates as D
from .compose import own_text

MAX_SOURCES = 3
MAX_ITEMS_PER_SOURCE = 6
VERDICT_RANK = {"clear": 0, "close": 1}


def _ord(day):
    try:
        return date.fromisoformat(str(day)[:10]).toordinal()
    except (TypeError, ValueError):
        return 0


def year_hit(text, posted, year):
    """The request names a year: the text names it, or the post was made in the 12 months before it (or in it)."""
    if not year:
        return True
    if str(year) in (text or ""):
        return True
    return bool(posted) and str(year - 1) <= str(posted)[:4] <= str(year)


def date_fields(p, extra, today, ts, year=None):
    """One pick's dates (posted, kept), and for a time-sensitive request its state from its own text."""
    it = p["item"]
    p["posted"], p["kept_first"] = D.posted_on(it, extra), D.first_kept(it)
    p["age_from"], p["today"] = p["posted"] or p["kept_first"], today
    if ts:
        own = own_text(it, extra)
        p["date_state"] = D.state_of(own, p["posted"], p["kept_first"], today, own=own)
        p["year_hit"] = year_hit(own, p["posted"], year)
    return p


def post_dates(result, extra, today, ts, year=None):
    """Sets each pick's "posted", "kept_first" and (time-sensitive) "date_state"; reorders and drops passed picks as
    above. Changes nothing for a request that is not time-sensitive."""
    allp = list(result.get("picks") or []) + list(result.get("wider") or [])
    for p in allp:
        it = p["item"]
        p["posted"] = D.posted_on(it, extra)
        p["kept_first"] = D.first_kept(it)
        p["age_from"] = p["posted"] or p["kept_first"]
        p["today"] = today
        if ts:
            own = own_text(it, extra)
            p["date_state"] = D.state_of(own, p["posted"], p["kept_first"], today, own=own)
            p["year_hit"] = year_hit(own, p["posted"], year)
    if not ts or not allp:
        return
    n_picks, n_wide = len(result.get("picks") or []), len(result.get("wider") or [])
    for p in result.get("spare") or []:   # clear fits past the count: one may take a passed pick's place
        if all(p is not q for q in allp):
            date_fields(p, extra, today, True, year)
            allp.append(p)
    passed = [p for p in allp if (p.get("date_state") or {}).get("state") == "passed"]
    live = [p for p in allp if p not in passed]
    if live and passed:   # never the lead and never an alternative while anything not passed fits
        result.setdefault("dropped", {})["passed"] = len(passed)
        allp = live
    def rank(p):
        st = (p.get("date_state") or {}).get("state")
        return (2 if st == "passed" else (1 if st == "old" else 0), VERDICT_RANK.get(p.get("verdict"), 1),
                0 if p.get("year_hit", True) else 1, -_ord(p.get("posted") or p.get("kept_first")))
    order = sorted(allp, key=rank)
    if order and allp and order[0] is not allp[0]:
        result.setdefault("dropped", {})["date_reorder"] = 1
    n_picks = max(1, n_picks)
    result["picks"], result["wider"] = order[:n_picks], order[n_picks:n_picks + n_wide]


def item_state(x, p, extra, today):
    """An item's state from its own when and about (the post's year for a date with none), and the post's text for
    the now-talk test."""
    own = own_text(p["item"], extra)
    text = " ".join(t for t in (x.get("when"), x.get("about")) if t)
    st = D.state_of(text, p.get("posted"), p.get("kept_first"), today, own=own)
    if st.get("date") and x.get("when") and not st.get("deadline"):
        # "apply by December 1" in the post, "December 1" as the item's when: a deadline
        at = own.lower().find(x["when"].lower())
        st["deadline"] = at >= 0 and bool(D.DEADLINE_WORD.search(own[max(0, at - 30):at]))
    return st


MAX_MORE = 2   # round 8, finding 94: the next posts with things, one "More in your saves:" line each


def good(x):
    """Round 8, finding 93: a thing that may be counted: it has words of the post's own about it, or the post lists it
    on a line of its own (extract.clean_items marks it "listed")."""
    return bool(x.get("about")) or bool(x.get("listed"))


def choose_items(result, extra, today, ts, year=None, notes=True, things=False, reads=None):
    """[(pick, [item, ...], more)] for the items answer, or None when the posts read name fewer than 2 good things.
    Each item: name, about, when, fit, n (its number in the answer), state, note (the date said to the person, for a
    time-sensitive request), stale_from (the post's month when its about says "now" and the post is old).
    Round 8: `reads` are the posts the details step read (the shown picks first, finding 94); with `things` (the request
    names a kind of thing) only things the model marked as that kind ("yes") are shown, unless fewer than 2 would be
    left over all posts (finding 93); only things with words count, and fewer than 2 make no items answer. The posts
    are shown by how many good things they give (most first; ties keep the composer's order). The next MAX_MORE posts
    with things are kept as result["items_more"]: [(pick, how many)]."""
    allp = list(reads) if reads is not None else list(result.get("picks") or []) + list(result.get("wider") or [])
    srcs = []
    for p in allp:
        got = [dict(x) for x in (p.get("facts") or {}).get("items") or [] if good(x)]
        if got:
            srcs.append([p, got])
    if things and sum(1 for _, its in srcs for x in its if x.get("fit") == "yes") >= 2:
        n = 0
        for s in srcs:
            n += sum(1 for x in s[1] if x.get("fit") != "yes")
            s[1] = [x for x in s[1] if x.get("fit") == "yes"]
        if n:
            result.setdefault("dropped", {})["items_not_the_kind"] = n
        srcs = [s for s in srcs if s[1]]
    for p, got in srcs:
        for x in got:
            if ts:
                st = item_state(x, p, extra, today)
                x["state"] = st["state"]
                x["date"] = st["date"].isoformat() if st.get("date") else None
                x["note"] = D.date_note(st, today) if notes else ""
                words = " ".join([x.get("name") or "", x.get("about") or "", x.get("when") or ""])
                x["year_hit"] = year_hit(words, p.get("posted"), year) if year else True
                # checker (rule 3 of finding 90): its own words name only years before the one asked for ("Design
                # award 2024" for "for 2026"): it contradicts the request, read by code, not by the model's "fit"
                named = [int(y) for y in D.YEAR.findall(words)]
                x["year_off"] = bool(year and named and max(named) < year)
            if x.get("about") and D.stale(x["about"], p.get("age_from"), today):
                x["stale_from"] = D.month_year(p.get("age_from"))
    if ts:
        def gone(x):
            return x.get("state") == "passed" or x.get("year_off")
        live = sum(1 for _, its in srcs for x in its if not gone(x))
        if live >= 2:   # a passed thing (or one of an earlier year) is never shown while 2 or more others fit
            n = 0
            for s in srcs:
                n += sum(1 for x in s[1] if gone(x))
                s[1] = [x for x in s[1] if not gone(x)]
            if n:
                result.setdefault("dropped", {})["items_passed"] = n
        for s in srcs:
            s[1].sort(key=lambda x: (2 if x.get("state") == "passed" else (1 if x.get("state") == "old" else 0),
                                     0 if x.get("year_hit", True) else 1, 0 if x.get("fit") == "yes" else 1))
        srcs = [s for s in srcs if s[1]]
        srcs.sort(key=lambda s: (all(x.get("state") in ("old", "passed") for x in s[1]),
                                 all(not x.get("year_hit", True) for x in s[1]),
                                 -_ord(s[0].get("posted") or s[0].get("kept_first"))))
    srcs = [s for s in srcs if s[1]]
    if sum(len(its) for _, its in srcs) < 2:
        result["items_more"] = []
        return None
    if reads is not None:   # round 8, finding 94: most good things first (a stable sort keeps the order before)
        # (for a time-sensitive request a post whose things are all old or passed still comes after the fresher)
        srcs.sort(key=lambda s: (ts and all(x.get("state") in ("old", "passed") for x in s[1]),
                                 -min(len(s[1]), MAX_ITEMS_PER_SOURCE)))
    out, n = [], 0
    for p, its in srcs[:MAX_SOURCES]:
        shown = its[:MAX_ITEMS_PER_SOURCE]
        for x in shown:
            n += 1
            x["n"] = n
        out.append((p, shown, len(its) - len(shown)))
    result["items_more"] = [(p, len(its)) for p, its in srcs[MAX_SOURCES:MAX_SOURCES + MAX_MORE]]
    return out


def stale_reason(p, today):
    """True when the pick's shown reason states a time-relative claim and the post is older than 60 days."""
    b = p.get("because") if p.get("because_backed") else None
    return bool(b) and D.stale(b, p.get("age_from"), today)


# ---------- round 8, finding 95: several asks in one message ----------
import re  # noqa: E402

MAX_PARTS = 3
PART_COUNT = 2
# the head nouns that make a part its own ask: kinds of thing (extract.THINGS) and kinds of post
_HEADS = (r"reels?|videos?|posts?|tutorials?|recipes?|workouts?|routines?|guides?|lessons?|things|stuff|dish(?:es)?|"
          r"dinners?|meals?|lunch(?:es)?|breakfasts?|snacks?|desserts?|songs?|movies?|tv shows|quotes?|articles?|reads|"
          r"librar(?:y|ies)|tools?|resources?|opportunit(?:y|ies)|programs?|programmes?|places?|spots?|books?|apps?|"
          r"products?|ideas?|tips?|websites?|sites?|courses?|internships?|scholarships?|fellowships?|grants?|events?|"
          r"restaurants?|cafes?|bars?|shops?|stores?|brands?|frameworks?|plugins?|extensions?|templates?|fonts?|icons?|"
          r"kits?|channels?|podcasts?|newsletters?|deadlines?|jobs?|hackathons?|competitions?|awards?")
HEAD = re.compile(rf"\b(?:{_HEADS})\b", re.I)
SEP_KEEP = re.compile(r"(\s*,\s*(?:(?:or|and|plus|also)\s+)?|\s+(?:or|and|plus|also)\s+)", re.I)
LEAD_WORDS = re.compile(r"^\W*(?:(?:hey|hi|ok(?:ay)?|so|please|pls)[,\s]+)*(?:(?:can|could|would|will) you\s+)?"
                        r"(?:please\s+)?(?:send|show|find|give|get|recommend)(?:\s+me)?\s+|^\W*(?:also|some|any)\s+", re.I)


def _lead_strip(x):
    """The words that only ask ("send me", "can you find", "also", "some"), left out from the start."""
    while True:
        y = LEAD_WORDS.sub("", x, count=1)
        if y == x:
            return x.strip()
        x = y


def _head(seg):
    """The segment's head noun, singular and lower case, or None."""
    from .retrieve import _stem
    found = HEAD.findall(seg)
    return _stem(found[0].lower()) if found else None


def split_asks(*texts):
    """Round 8, finding 95: the parts of a message (or a goal) that is a list of different kinds of thing ("startup
    motivation reels, opportunities to pursue soon, or things with deadlines"): at most MAX_PARTS, each with its own
    head noun, each in its own words; None when it is one ask ("chicken and rice recipes", "quick and easy dinners",
    "pasta or rice dishes": a part with no head noun of its own belongs to the next one). The person's message is read
    first, then the goal."""
    for text in texts:
        t = _lead_strip(" ".join((text or "").split()).strip(" ?!."))
        pieces = SEP_KEEP.split(t)   # segment, separator, segment, ...
        segs = [(pieces[i].strip(" ,.;:?!"), (pieces[i + 1] if i + 1 < len(pieces) else "").strip().lower())
                for i in range(0, len(pieces), 2)]
        segs = [(_lead_strip(x), sep) for x, sep in segs]   # "and show me ..."
        segs = [(x, sep) for x, sep in segs if x]
        if len(segs) < 2:
            continue
        # a segment with no head noun of its own: before "and" / "or" it is a word of the next part ("quick and easy
        # dinners", "chicken and rice recipes"); before a comma, or last, it ends the part before it ("things with
        # deadlines and prizes, or ...")
        parts, carry, last_word = [], "", {}
        for x, sep in segs:
            word = sep.replace(",", "").strip() or "and"
            if _head(x):
                parts.append(f"{carry} {x}".strip())
                carry = ""
            elif parts and (sep.startswith(",") or not sep) and not carry:
                parts[-1] = f"{parts[-1]} {last_word.get(len(parts) - 1, 'and')} {x}"
            else:
                carry = f"{carry} {x} {word}".strip()
            if _head(x):
                last_word[len(parts) - 1] = word
        if carry:
            continue
        parts = [_lead_strip(p) for p in parts]
        heads = [_head(p) for p in parts]
        if len(parts) < 2 or len(set(heads)) < len(heads) or len(parts) > MAX_PARTS:
            continue
        if any(_bare(p) for p in parts):   # checker, round 8: "tools and resources for designers", "cafes and
            continue                       # restaurants in lisbon": a bare kind word shares the others' topic (one ask)
        return parts
    return None


# the small words a part may hold beside its head noun and still be bare
_BARE_SKIP = set("a an the some any good best great new more other few nice cool useful".split())


def _bare(part):
    """Checker, round 8: a part that is only its head noun ("tools", "some apps") has no topic of its own: it is a
    word of the same ask as the parts beside it."""
    words = [w for w in re.findall(r"[^\W_]+(?:['’/][^\W_]+)*", part.lower()) if w not in _BARE_SKIP]
    return len(words) <= 1 and bool(_head(part))

