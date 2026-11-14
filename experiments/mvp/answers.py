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
    n_picks = len(result.get("picks") or [])
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
    result["picks"], result["wider"] = order[:max(1, n_picks)], order[max(1, n_picks):]


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


def choose_items(result, extra, today, ts, year=None, notes=True):
    """[(pick, [item, ...], more)] for the items answer, or None when the picks' text names fewer than 2 things.
    Each item: name, about, when, fit, n (its number in the answer), state, note (the date said to the person, for a
    time-sensitive request), stale_from (the post's month when its about says "now" and the post is old)."""
    allp = list(result.get("picks") or []) + list(result.get("wider") or [])
    srcs = []
    for p in allp:
        got = (p.get("facts") or {}).get("items") or []
        if not got:
            continue
        its = []
        for x in got:
            x = dict(x)
            if ts:
                st = item_state(x, p, extra, today)
                x["state"] = st["state"]
                x["date"] = st["date"].isoformat() if st.get("date") else None
                x["note"] = D.date_note(st, today) if notes else ""
                x["year_hit"] = year_hit(" ".join([x.get("name") or "", x.get("about") or "", x.get("when") or ""]),
                                         p.get("posted"), year) if year else True
            if x.get("about") and D.stale(x["about"], p.get("age_from"), today):
                x["stale_from"] = D.month_year(p.get("age_from"))
            its.append(x)
        srcs.append([p, its])
    if ts:
        live = sum(1 for _, its in srcs for x in its if x.get("state") != "passed")
        if live >= 2:   # a passed thing is never shown while 2 or more that have not passed fit
            n = 0
            for s in srcs:
                n += sum(1 for x in s[1] if x.get("state") == "passed")
                s[1] = [x for x in s[1] if x.get("state") != "passed"]
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
        return None
    out, n = [], 0
    for p, its in srcs[:MAX_SOURCES]:
        shown = its[:MAX_ITEMS_PER_SOURCE]
        for x in shown:
            n += 1
            x["n"] = n
        out.append((p, shown, len(its) - len(shown)))
    return out


def stale_reason(p, today):
    """True when the pick's shown reason states a time-relative claim and the post is older than 60 days."""
    b = p.get("because") if p.get("because_backed") else None
    return bool(b) and D.stale(b, p.get("age_from"), today)
