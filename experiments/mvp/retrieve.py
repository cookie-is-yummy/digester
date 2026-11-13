"""PROTOTYPE ONLY - candidate items for one spec, from the person's own library only (BRIEF-10 rule 1).

Source library: runs each search of the spec through the library's Q8 engine (deep ID lists; the same text on the same
library build reuses its ranked list), fuses the lists, then applies in code: platform and kind filters, the person's
excluded kinds and platforms, creators and collections (and the ones to avoid), the saved-after (inclusive) and
saved-before (exclusive) dates, items already sent by this rule (rule 4), items the person gave 👎 (rule 9), anything
containing an avoided word, and friends' posts (rule 5, already dropped by LibraryView). Then the order asked for.
Source recent: what they kept in the period, newest first, no search. Source items: fixed ids set by code.
"""
import hashlib
import json
import os
import random
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from . import config

KIND_BOOST = {"save": 1.3, "collection": 1.3, "share_self": 1.3, "playlist": 1.25, "like": 1.1, "watch": 1.0, "view": 0.9}


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"\s+", " ", s).strip()


def _stem(word):
    """Singular form: berries -> berry, tomatoes -> tomato, dishes -> dish, noodles -> noodle, eggs -> egg."""
    w = norm(word)
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("ches", "shes", "sses", "xes", "zes", "oes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
ENDINGS = ("y", "ey", "ed", "ing")                      # creamy, creamed
# short words hide inside unrelated ones ("nut" in "minutes", "oil" in "boil"), so their compounds are listed
COMPOUNDS = {"nut": {"peanut", "walnut", "hazelnut", "chestnut", "coconut", "nutty", "nutella"},
             "egg": {"eggy"}, "ham": {"hammy"}, "soy": {"soya", "soybean"}}


def contains_word(text, word):
    """For avoided words. Matches whole words in singular or plural ('egg' and 'eggs', 'berry' and 'berries'), a few
    endings ('cream' and 'creamy'), and compounds: a word of 4 letters or more also matches at the end of a longer
    word ('berry' in 'strawberries', 'cream' in 'icecream'); shorter ones only through the list above, so 'nut' does
    not match 'minutes' and 'oil' does not match 'boil'. A phrase ('ice cream') must appear as that phrase."""
    stems = [_stem(w) for w in WORD.findall(norm(word))]
    if not stems:
        return False
    toks = WORD.findall(norm(text))
    tstems = [_stem(t) for t in toks]
    if len(stems) > 1:
        return any(tstems[i:i + len(stems)] == stems for i in range(len(tstems) - len(stems) + 1))
    w = stems[0]
    if len(w) < 2:
        return False
    for tok, ts in zip(toks, tstems):
        if ts == w or tok in COMPOUNDS.get(w, ()) or ts in COMPOUNDS.get(w, ()):
            return True
        if tok.startswith(w) and tok[len(w):] in ENDINGS:
            return True
        if w.endswith("e") and tok == w[:-1] + "y":  # cheese -> cheesy
            return True
        if len(w) >= 4 and ts.endswith(w):
            return True
    return False


def date_for(it, kinds):
    """The date a filter is checked against: when the person did the thing they asked about ('liked this month' uses
    the like), otherwise when they kept the item."""
    dates = [it.dates[k] for k in kinds if k in it.kinds and it.dates.get(k)]
    return max(dates)[:10] if dates else it.kept_on()


def _squash(s):
    return re.sub(r"[\W_]+", "", norm(s))


def name_matches(name, wanted):
    """A creator or collection name the person gave matches the item's: the same letters and digits (case, spaces,
    '@' and punctuation ignored), or, for a name of 4 or more, contained in it ('blender guru' in 'Blender Guru Pro')."""
    a, b = _squash(name), _squash(wanted)
    if not a or not b:
        return False
    return a == b or (len(b) >= 4 and b in a)


def _library_stamp(lib):
    """Changes when the library is rebuilt, so ranked lists cached for the old build are not reused."""
    path = os.path.join(lib, "corpus", "items.jsonl")
    try:
        st = os.stat(path)
        return f"{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        return "none"


def _search(pool, lib, query):
    """One search, never read as "nothing found" when it failed (fix pass, finding 23): the engine ranks the whole
    library, so an empty list from a library that has items is a fault. It is tried once more, then it is an error
    (the run fails and says "try again"; a timed send is retried), and it is never cached."""
    r = pool.search(lib, query)
    if not r.get("ids"):
        r = pool.search(lib, query)
        if not r.get("ids"):
            raise RuntimeError("the search returned no ranking")
    return r


def ranked(pool, lib, query, store=None, now=None):
    """The engine's ranked IDs for one search text. The engine is deterministic for a text (consistency note); the
    same text on the same library build reuses the list (section 4), which also saves the search time."""
    if store is None or not config.RANKED_CACHE_HOURS:
        return _search(pool, lib, query)
    now = now or datetime.now(timezone.utc)
    key = hashlib.sha256(json.dumps([os.path.abspath(lib), _library_stamp(lib), " ".join(query.lower().split()),
                                     config.SEARCH_DEPTH]).encode()).hexdigest()
    since = (now - timedelta(hours=config.RANKED_CACHE_HOURS)).astimezone(timezone.utc).isoformat(timespec="seconds")
    hit = store.cache_get("ranked_cache", key, since)
    # an empty list kept by an older build is never reused, nor a stand-in ranking kept before review fix X5
    if hit is not None and hit.get("ids") and hit.get("mode") in (None, "normal"):
        return {"ids": hit["ids"], "mode": hit.get("mode"), "cost_usd": 0.0, "cached": True}
    r = _search(pool, lib, query)
    if r.get("mode") != "normal" or r.get("degraded"):
        # review fix X5: a stand-in ranking (the keyword fallback after a failed query embedding, or the raw query
        # when the rewrite failed) is used for this run only; kept, it would stand for days in place of the real one
        return r
    store.cache_put("ranked_cache", key, {"ids": r["ids"], "mode": r.get("mode")}, at=now, library=lib, mode=r.get("mode"))
    return r


def keep(it, c, exclude_kinds=(), exclude_platforms=()):
    """The filters every source shares: platforms and kinds asked for, the person's own exclusions ("don't use my
    likes": an item kept only by a like is left out, one also saved stays), creators and collections."""
    if c.platforms and it.platform not in c.platforms:
        return False
    if exclude_platforms and it.platform in exclude_platforms:
        return False
    if c.kinds and not (it.kinds & set(c.kinds)):
        return False
    if exclude_kinds and it.kinds and not (it.kinds - set(exclude_kinds)):
        return False
    if c.creators and not any(name_matches(it.creator or "", w) for w in c.creators):
        return False
    if c.avoid_creators and any(name_matches(it.creator or "", w) for w in c.avoid_creators):
        return False
    if c.collections and not any(name_matches(col, w) for col in it.collections for w in c.collections):
        return False
    if c.avoid_collections and any(name_matches(col, w) for col in it.collections for w in c.avoid_collections):
        return False
    return True


def _period(c, now):
    saved_after = c.saved_after
    if c.since_days and not saved_after:  # a relative period, worked out at each run
        saved_after = ((now or datetime.now(timezone.utc)) - timedelta(days=c.since_days)).date().isoformat()
    return saved_after, c.saved_before


def in_period(kept, saved_after, saved_before):
    """saved_after is inclusive, saved_before exclusive (section 11)."""
    if saved_after and (not kept or kept < saved_after):
        return False
    if saved_before and (not kept or kept >= saved_before):
        return False
    return True


def candidates(pool, view, spec, exclude=(), disliked=(), creator_weights=None, k=config.CANDIDATES, now=None,
               store=None, exclude_kinds=(), exclude_platforms=(), seed=None, only=None):
    """Candidates for one spec, best first (or in the order the spec asks for). `seed` makes order "random" repeatable
    for one run (a rule's slot, or an ask's day). `only` (a set of item ids) keeps just those items: the items an
    import added, for a new_items rule (slice 5)."""
    c = spec.content
    exclude, disliked = set(exclude), set(disliked)
    if only is not None:   # everything else is left out, whatever the source
        only = set(only)
        exclude |= {iid for iid in view.items if iid not in only}
    saved_after, saved_before = _period(c, now)
    if c.source == "items":   # fixed ids set by code (an earlier answer sent again): in that order, nothing searched
        out = [view.get(i) for i in c.item_ids if i not in disliked]
        return [it for it in out if it is not None][:k], {"cost_usd": 0.0, "modes": [], "fused": len(c.item_ids)}
    if c.source == "recent":  # what they kept in the period, newest first; no search
        rows = []
        for it in view.items.values():
            if it.id in exclude or it.id in disliked or not keep(it, c, exclude_kinds, exclude_platforms):
                continue
            kept = date_for(it, c.kinds)
            if not in_period(kept, saved_after, saved_before):
                continue
            if any(contains_word(it.caption, w) for w in c.avoid):
                continue
            rows.append((kept or "", it.id, it))
        rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [it for *_, it in rows[:k]], {"cost_usd": 0.0, "modes": [], "fused": len(rows)}
    scores, cost, modes, cached = {}, 0.0, set(), 0
    if not view.items:   # an empty library: nothing to rank (the only time no ranking is right)
        return [], {"cost_usd": 0.0, "modes": [], "fused": 0, "cached": 0}
    for q in c.searches:
        r = ranked(pool, view.lib, q, store=store, now=now)
        cost += r["cost_usd"] or 0.0
        cached += bool(r.get("cached"))
        modes.add(r["mode"])
        for rank, iid in enumerate(r["ids"]):
            scores[iid] = scores.get(iid, 0.0) + 1.0 / (60 + rank)
    creator_weights = creator_weights or {}
    out = []
    for iid, s in scores.items():
        it = view.get(iid)
        if it is None or iid in exclude or iid in disliked:
            continue
        if not keep(it, c, exclude_kinds, exclude_platforms):
            continue
        if not in_period(date_for(it, c.kinds), saved_after, saved_before):
            continue
        if any(contains_word(it.caption, w) for w in c.avoid):
            continue
        boost = max((KIND_BOOST.get(kd, 1.0) for kd in it.kinds), default=1.0)
        if c.extract and len(it.caption) >= 200:
            boost *= 1.2  # details are only usable when the item's own text holds them
        boost *= creator_weights.get(it.creator, 1.0)
        out.append((s * boost, iid, it))
    out.sort(key=lambda x: (-x[0], x[1]))
    top = [it for *_, it in out[:k]]
    if c.order in ("newest", "oldest"):   # the best matches, then by date
        top.sort(key=lambda it: (date_for(it, c.kinds) or "", it.id), reverse=(c.order == "newest"))
    elif c.order == "random":
        rnd = random.Random(str(seed if seed is not None else "") + "|" + "|".join(c.searches))
        rnd.shuffle(top)
    return top, {"cost_usd": cost, "modes": sorted(m for m in modes if m), "fused": len(scores), "cached": cached}
