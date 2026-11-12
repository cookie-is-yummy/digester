"""PROTOTYPE ONLY - candidate items for one spec, from the person's own library only (BRIEF-10 rule 1).

Runs each search of the spec through the library's Q8 engine (deep ID lists), fuses the lists, then applies in code:
platform and kind filters, the saved-after/before dates, items already sent by this rule (rule 4), items the person
gave 👎 (rule 9), anything containing an avoided word, and friends' posts (rule 5, already dropped by LibraryView).
"""
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


def candidates(pool, view, spec, exclude=(), disliked=(), creator_weights=None, k=config.CANDIDATES, now=None):
    c = spec.content
    saved_after = c.saved_after
    if c.since_days and not saved_after:  # a relative period, worked out at each run
        saved_after = ((now or datetime.now(timezone.utc)) - timedelta(days=c.since_days)).date().isoformat()
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
        kept = date_for(it, c.kinds)
        if saved_after and (not kept or kept < saved_after):
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
