"""PROTOTYPE ONLY - candidate items for one spec, from the person's own library only (BRIEF-10 rule 1).

Runs each search of the spec through the library's Q8 engine (deep ID lists), fuses the lists, then applies in code:
platform and kind filters, the saved-after/before dates, items already sent by this rule (rule 4), items the person
gave 👎 (rule 9), anything containing an avoided word, and friends' posts (rule 5, already dropped by LibraryView).
"""
import re
import unicodedata

from . import config

KIND_BOOST = {"save": 1.3, "collection": 1.3, "share_self": 1.3, "playlist": 1.25, "like": 1.1, "watch": 1.0, "view": 0.9}


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"\s+", " ", s).strip()


def contains_word(text, word):
    """Whole word, or a word that starts with it: 'cream' matches 'creams' and 'creamy'."""
    w = norm(word)
    return bool(w) and re.search(r"(?<!\w)" + re.escape(w), norm(text)) is not None


def candidates(pool, view, spec, exclude=(), disliked=(), creator_weights=None, k=config.CANDIDATES):
    c = spec.content
    scores, cost, modes = {}, 0.0, set()
    for q in c.searches:
        r = pool.search(view.lib, q)
        cost += r["cost_usd"] or 0.0
        modes.add(r["mode"])
        for rank, iid in enumerate(r["ids"]):
            scores[iid] = scores.get(iid, 0.0) + 1.0 / (60 + rank)
    exclude, disliked = set(exclude), set(disliked)
    creator_weights = creator_weights or {}
    out = []
    for iid, s in scores.items():
        it = view.get(iid)
        if it is None or iid in exclude or iid in disliked:
            continue
        if c.platforms and it.platform not in c.platforms:
            continue
        if c.kinds and not (it.kinds & set(c.kinds)):
            continue
        kept = it.kept_on()
        if c.saved_after and (not kept or kept < c.saved_after):
            continue
        if c.saved_before and (not kept or kept > c.saved_before):
            continue
        if any(contains_word(it.caption, w) for w in c.avoid):
            continue
        boost = max((KIND_BOOST.get(kd, 1.0) for kd in it.kinds), default=1.0)
        if c.extract != "none" and len(it.caption) >= 200:
            boost *= 1.2  # details are only usable when the item's own text holds them
        boost *= creator_weights.get(it.creator, 1.0)
        out.append((s * boost, it))
    out.sort(key=lambda x: -x[0])
    return [it for _, it in out[:k]], {"cost_usd": cost, "modes": sorted(m for m in modes if m), "fused": len(scores)}
