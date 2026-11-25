"""PROTOTYPE ONLY - round 12, D (DESIGN.md section 19.D): the fact sheet of one history question, built by code.

The sheet is the seam between the two builders of round 12: builder W's writer chooses what to say and how, from
this sheet ONLY; every number, date and name in it is computed here from the person's own record (history.Record's
events, re-read with their hour), the themes (themes.py) and the official lengths (lengths.py). Nothing here calls a
model or the network. Every theme name in it is safe to show (sensitive themes are left out: their items fall
under no theme, `unthemed`). Numbers are exact counts, or rounded here (hours to one decimal, shares to three).

Keys (each may be absent or empty; see DESIGN 19.D for what each means): question, kind, window, filters, totals,
previous, themes, channels, periods, topics, when, new, stopped, library, items, offers; added by D: fields,
change, unthemed, window_totals, cannot_see.

Lengths: the export holds no watch time. `length_hours` is the total LENGTH of the distinct videos opened (each video
once in a window), where the official length is known (`length_known_share` of the YouTube videos in scope); never
time watched.
"""
import os
import re
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import history as Hm

KIND_OF = {"top_channels": "channels", "top_topics": "top", "top_items": "top", "count": "count", "list": "top",
           "on_day": "day", "first": "first", "last": "last", "timeline": "count", "compare": "compare_windows",
           "compare_topics": "compare_topics", "changed": "changed", "top": "top"}
THEMES_MAX, CHANNELS_MAX, EXAMPLES = 8, 10, 3
NEW_MIN_ITEMS, NEW_MIN_SHARE, ABSENT_RATIO = 5, 0.02, 0.25   # "new": at least 5 items and 2% now, and under a
# quarter of that share in the window before ("stopped": the reverse)
NEW_CHANNEL_MIN, NEW_CHANNEL_DAYS = 5, 2
NEW_PREV_MAX = 5   # round 12, pass 2 fix: "new" / "stopped" with at most 5 videos on the other side
SAVED_KINDS = ("save", "collection", "share_self", "playlist")
LENGTH_CAP_S = 3 * 3600   # lengths are summed for videos up to 3 hours; longer ones are counted apart (over_3h)
_LOCK = threading.Lock()
_IDX = {}


def sheet_kind(q):
    if q.kind == "top_channels" and q.topics_too:
        return "top"
    return KIND_OF.get(q.kind, "top")


# ================================================================ the index: every event with its local hour
class Index:
    """numpy arrays over the view's items and their events (friends' posts are not in the view; a share to a friend is
    not an event), dated in the person's time zone like history.Record."""

    def __init__(self, view, tz):
        import json
        import numpy as np
        zone = ZoneInfo(tz)
        self.ids = sorted(view.items)
        self.pos = {i: k for k, i in enumerate(self.ids)}
        it_, day_, hour_, wd_, kind_, sec_ = [], [], [], [], [], []
        self.kinds = ["watch", "view", "like", "save", "collection", "share_self", "playlist"]
        kcode = {k: n for n, k in enumerate(self.kinds)}
        path = os.path.join(view.lib, "corpus", "interactions.jsonl")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    k = self.pos.get(r.get("item_id"))
                    kc = kcode.get(r.get("kind"))
                    at = r.get("at")
                    if k is None or kc is None or not at:
                        continue
                    try:
                        d = datetime.fromisoformat(at)
                    except ValueError:
                        continue
                    d = d.astimezone(zone) if d.tzinfo else d.replace(tzinfo=zone)
                    it_.append(k)
                    sec_.append(int(d.timestamp()))
                    day_.append(d.toordinal())
                    hour_.append(d.hour)
                    wd_.append(d.weekday())
                    kind_.append(kc)
        self.it = np.array(it_, dtype=np.int32)
        self.day = np.array(day_, dtype=np.int32)
        self.hour = np.array(hour_, dtype=np.int8)
        self.wd = np.array(wd_, dtype=np.int8)
        self.kind = np.array(kind_, dtype=np.int8)
        # round 12, pass 6 (X1: "the last" was the day's first video): every event's instant, so a first or a last
        # is ordered by its time (the person's local time for the words, the instant for the order)
        self.sec = np.array(sec_, dtype=np.int64)
        self.zone = zone
        self.platform = np.array([0 if view.items[i].platform == "youtube" else 1 for i in self.ids], dtype=np.int8)
        names = sorted({view.items[i].creator for i in self.ids if view.items[i].creator})
        self.creators = names
        cpos = {c: n for n, c in enumerate(names)}
        self.creator = np.array([cpos.get(view.items[i].creator, -1) for i in self.ids], dtype=np.int32)

    def kind_mask(self, kinds):
        import numpy as np
        codes = [n for n, k in enumerate(self.kinds) if k in kinds]
        return np.isin(self.kind, codes)


class ItemFacts:
    """Per item: theme, field, length, Short (from the builds of themes.py and lengths.py, by their stamps)."""

    def __init__(self, view, idx):
        import numpy as np
        from . import lengths as L
        from . import themes as T
        self.th = T.load(view.lib)
        rows = L.load()
        n = len(idx.ids)
        self.theme = np.full(n, -1, dtype=np.int32)
        self.field = np.full(n, -1, dtype=np.int32)
        self.length = np.full(n, -1, dtype=np.int64)
        self.raw_length = np.full(n, -1, dtype=np.int64)
        self.short = np.full(n, -1, dtype=np.int8)
        canon = {}   # two themes of one name (a field cut in two by the clusters) count as one, under the first
        if self.th is not None:
            for t in sorted(self.th.themes):
                nm = self.th.shown(t)
                if nm is not None:
                    canon[t] = canon.get(nm.lower(), t)
                    canon.setdefault(nm.lower(), t)
        self.canon = {t: v for t, v in canon.items() if isinstance(t, int)}
        # round 12, pass 2 (T3): the broad level, the AREA of each theme (its category in the fixed list of
        # theme_name_v2: "gaming", "comedy", "science"; words a person uses), so an answer can say what most of a
        # window was; 50 themes of 5% each say nothing at the top
        self.area = np.full(n, -1, dtype=np.int32)
        self.area_names = []
        area_of = {}
        if self.th is not None:
            for t in self.canon.values():
                a = theme_area(self.th, t)
                if a is not None:
                    if a not in self.area_names:
                        self.area_names.append(a)
                    area_of[t] = self.area_names.index(a)
        for k, i in enumerate(idx.ids):
            it = view.items[i]
            if self.th is not None:
                t = self.th.theme_id(i)
                if t is not None and t in canon:
                    self.theme[k] = canon[t]
                    self.area[k] = area_of.get(canon[t], -1)
                f = self.th.field_id(i)
                if f is not None:
                    self.field[k] = f
            if it.platform == "youtube":
                ln, sh = L.length_of(it, rows)
                if ln:
                    self.raw_length[k] = int(ln)
                    # a video over LENGTH_CAP_S (a stream, a 10-hour loop) is no measure of attention: it is left out
                    # of every length sum and counted as `over_3h`
                    self.length[k] = int(ln) if ln <= LENGTH_CAP_S else -2
                    self.short[k] = 1 if sh else 0


AREA_SHOWN = {"film and tv": "film and TV", "diy and making": "DIY and making", "nature and animals": "nature and animals",
              "family and kids": "family and kids", "art and design": "art and design", "food and cooking": "food and cooking"}


def theme_area(th, tid):
    """The area (category) of a theme as a person says it, or None ("other", none, or a sensitive one)."""
    from . import themes as T
    t = th.themes.get(tid) or {}
    cat = t.get("category") or (th.fields.get(t.get("field")) or {}).get("category")
    if not cat or cat == "other" or cat in T.SENSITIVE_CATEGORIES or th.shown(tid) is None:
        return None
    return AREA_SHOWN.get(cat, cat)


def index(view, tz):
    from . import lengths as L
    from . import themes as T
    path = os.path.join(view.lib, "corpus", "interactions.jsonl")
    try:
        st = os.stat(path)
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        stamp = None

    def mt(p):
        try:
            return os.stat(p).st_mtime_ns
        except OSError:
            return None
    dstamp = (mt(os.path.join(T.folder(view.lib), "space.npz")), mt(os.path.join(L.folder(), "lengths.jsonl")))
    key = (id(view), view.lib, tz, stamp)
    with _LOCK:
        hit = _IDX.get("idx")
        if hit and hit[0] == key:
            idx = hit[1]
        else:
            idx = None
    if idx is None:
        idx = Index(view, tz)
        with _LOCK:
            _IDX["idx"] = (key, idx)
            _IDX.pop("facts", None)
    with _LOCK:
        hit = _IDX.get("facts")
        if hit and hit[0] == (key, dstamp):
            return idx, hit[1]
    facts = ItemFacts(view, idx)
    with _LOCK:
        _IDX["facts"] = ((key, dstamp), facts)
    return idx, facts


# ================================================================ helpers
def _iso(o):
    return date.fromordinal(int(o)).isoformat()


def _hours(seconds):
    return round(float(seconds) / 3600.0, 1)


def _share(a, b):
    # round 12, pass 6 (X13: 113 of 1,514 is 7.46%, stored as 0.075 and said 8%): four places, so a share rounds once
    return round(a / b, 4) if b else 0.0


def topic_items(view, rec, idx, facts, phrase):
    """(item positions of a topic, how it was matched): the themes it maps to by code (themes.for_topic) plus every
    item whose own text holds its words."""
    import numpy as np
    from . import themes as T
    memo = facts.__dict__.setdefault("_topics", {})
    if phrase in memo:
        return memo[phrase]
    words = np.array([Hm.holds(view.items[i].caption or "", phrase) for i in idx.ids], dtype=bool)
    hits = {idx.ids[k] for k in np.nonzero(words)[0].tolist()}
    tids = T.for_topic(view, rec, phrase, facts.th, hits=hits) if facts.th is not None else []
    # a theme counted under another of the same name (ItemFacts) is matched by that one
    tids = sorted({int(facts.canon.get(t, t)) for t in tids})
    by_theme = np.isin(facts.theme, tids) if tids else np.zeros(len(idx.ids), bool)
    memo[phrase] = out = (by_theme | words, tids, int(by_theme.sum()), int(words.sum()))
    return out


# ---------- the brain's tools, step 1 (design/brain_v1/SPEC.md 2.2, 8.4, 11.3): the scope of a tool call. Every
# function here is used only when a query sets the new HistoryQuery fields or a caller asks for the sensitive topics
# to be left out; with neither, sheet() runs exactly as before.
def _ranked(counter, q, default_n):
    """The rows of a ranking: the `default_n` largest (Counter.most_common, as before) unless the query asks for
    another number (`q.top`) or for the smallest first (`q.order == "least"`: fewest first, ties by key)."""
    n = default_n if q is None or getattr(q, "top", None) is None else q.top
    if q is None or getattr(q, "order", "most") != "least":
        return counter.most_common(n)
    return sorted(counter.items(), key=lambda kv: (kv[1], kv[0]))[:n]


def _no_shorts(q):
    """Without Shorts: today's "without shorts", or a tool's `length: long` (videos KNOWN to be long, X6)."""
    return bool(getattr(q, "without_shorts", False) or getattr(q, "length", "any") == "long")


def slug(name):
    """An area's or a collection's slug in a ref: "art and design" -> "art-and-design"."""
    return re.sub(r"[^a-z0-9]+", "-", Hm.strip_accents((name or "").lower())).strip("-")


def channel_key(name):
    """A channel's key in a ref: "c" + the first 8 hex of sha1 of its normalised name (history._squash)."""
    import hashlib
    return "c" + hashlib.sha1(Hm._squash(name).encode("utf-8")).hexdigest()[:8]


def ref_mask(view, idx, facts, ref):
    """Per item (the index's order): the items a typed ref names. A ref of an unknown form names nothing."""
    import numpy as np
    n = len(idx.ids)
    form, _, val = (ref or "").partition(":")
    if form == "area":
        hit = [k for k, a in enumerate(facts.area_names) if slug(a) == val]
        return np.isin(facts.area, hit) if hit else np.zeros(n, bool)
    if form == "theme":
        try:
            tid = int(val)
        except ValueError:
            return np.zeros(n, bool)
        return facts.theme == int(facts.canon.get(tid, tid))
    if form == "channel":
        cids = [k for k, c in enumerate(idx.creators) if channel_key(c) == val]
        return np.isin(idx.creator, cids) if cids else np.zeros(n, bool)
    if form == "collection":
        return np.array([any(slug(c) == val for c in (view.items[i].collections or [])) for i in idx.ids], dtype=bool)
    if form == "words":
        return np.array([bool(val) and Hm.holds(view.items[i].caption or "", val) for i in idx.ids], dtype=bool)
    if form == "topic":
        # the brain's tools (toolfix 2: find gave no match for a topic the turn had unlocked): the items of one
        # sensitive topic (sensitive_items' topic of each item); the tools accept this form only for the turn's unlock
        topics = sensitive_items(view, idx, facts, None)[1]
        return np.array([bool(val) and t == val for t in topics], dtype=bool)
    return np.zeros(n, bool)


def scope_mask(view, idx, facts, q):
    """Per item: the items a query's scope keeps: any of `only_refs` (an OR), none of `exclude_refs` (a NOT), and for
    `length == "short"` the known Shorts and the Instagram reels. (`length == "long"` is the without-Shorts filter.)"""
    import numpy as np
    n = len(idx.ids)
    keep = np.ones(n, bool)
    only = list(getattr(q, "only_refs", None) or [])
    if only:
        anym = np.zeros(n, bool)
        for r in only:
            anym |= ref_mask(view, idx, facts, r)
        keep &= anym
    for r in getattr(q, "exclude_refs", None) or []:
        keep &= ~ref_mask(view, idx, facts, r)
    if getattr(q, "length", "any") == "short":
        reel = np.array([idx.platform[k] == 1 and view.items[i].media in ("reel", "video")
                         for k, i in enumerate(idx.ids)], dtype=bool)
        keep &= (facts.short == 1) | reel
    return keep


def _scoped(q):
    return bool(getattr(q, "only_refs", None) or getattr(q, "exclude_refs", None)
                or getattr(q, "length", "any") == "short")


def sensitive_items(view, idx, facts, unlock=None):
    """Per item: (hidden, topic) arrays. Hidden: an item of a theme in a sensitive category (or a theme marked
    sensitive) or one whose own text profile.sensitive flags; `topic`: the sensitive topic it is about (the theme's
    category, else outside.sensitive_topic of its text). An item of the `unlock` topic is not hidden (8.4: the unlock is
    per topic, set by code from their message)."""
    import numpy as np
    from . import outside as O
    from . import profile as P
    from . import themes as T
    memo = facts.__dict__.setdefault("_sensitive", {})
    if "all" not in memo:
        th = facts.th
        topics = []
        for i in idx.ids:
            topic = None
            if th is not None:
                t = th.theme_id(i)
                meta = th.themes.get(t) if t is not None else None
                if meta:
                    cat = meta.get("category") or (th.fields.get(meta.get("field")) or {}).get("category")
                    if cat in T.SENSITIVE_CATEGORIES:
                        topic = cat
                    elif meta.get("sensitive"):
                        # a sensitive theme keeps no name nor category in its build: the item's own words say its
                        # topic, else it is of no topic a message can unlock
                        topic = O.sensitive_topic([view.items[i].caption or ""]) or "sensitive"
            cap = view.items[i].caption or ""
            if topic is None and P.sensitive(cap):
                topic = O.sensitive_topic([cap]) or "sensitive"
            topics.append(topic)
        memo["all"] = (np.array([t is not None for t in topics], dtype=bool), topics)
    hid, topics = memo["all"]
    if unlock:
        hid = hid & np.array([t != unlock for t in topics], dtype=bool)
    return hid, topics


# ---------- the brain's read tools, after the thin live slice (toolfix 1, 4, 8): used only when sheet() is called with
# hide_sensitive (the brain's tools); today's sheets are unchanged
def _reel_mask(view, idx, facts):
    """Per item: an Instagram reel or video post (scope_mask's own test for `length == "short"`), memoised."""
    import numpy as np
    memo = facts.__dict__.setdefault("_reel", {})
    if "all" not in memo:
        memo["all"] = np.array([idx.platform[k] == 1 and view.items[i].media in ("reel", "video")
                                for k, i in enumerate(idx.ids)], dtype=bool)
    return memo["all"]


def _reels(view, idx, facts, items):
    """How many of `items` are Instagram reels or videos: `totals.shorts` counts YouTube Shorts only, while the
    length filter "short" takes both (the attack's area_oct_nogaming: shorts 0 with 4 reels in it)."""
    return int(_reel_mask(view, idx, facts)[items].sum()) if len(items) else 0


def friends_in(view, tz, kinds, plats, so, eo, q=None):
    """How many friends' posts (left out of every count, rule 5) the result's window, base, platforms and filters would
    have held: an event of the base's kinds on a day of the window (the person's time zone), on that weekday when one is
    asked, a reel or video when only the short ones are asked, none when only the long ones are (a friend's post is
    Instagram's). A friend's post is never placed in a theme, an area, a channel or a collection, so under an `only`
    scope none is counted; an `exclude` leaves them in. Reads view.friend_events (libview); 0 when it has none."""
    evs = getattr(view, "friend_events", None) or []
    if not evs or (q is not None and (getattr(q, "only_refs", None) or getattr(q, "length", "any") == "long")):
        return 0
    zone = ZoneInfo(tz)
    short = q is not None and getattr(q, "length", "any") == "short"
    wd = getattr(q, "weekday", None) if q is not None else None
    hit = set()
    for fid, kind, at, platform, media in evs:
        if kind not in kinds or platform not in plats or (short and media not in ("reel", "video")):
            continue
        try:
            d = datetime.fromisoformat(at)
        except (TypeError, ValueError):
            continue
        d = d.astimezone(zone) if d.tzinfo else d.replace(tzinfo=zone)
        o = d.toordinal()
        if (so is not None and o < so) or (eo is not None and o > eo) or (wd is not None and d.weekday() != wd):
            continue
        hit.add(fid)
    return len(hit)


class _Over:
    """A stand-in over an object with some attributes replaced (the unlocked topic's rows are built by the same row
    builders as every other row, over arrays that hold only the topic)."""

    def __init__(self, base, **over):
        self.__dict__.update(over)
        self.__dict__["_base"] = base

    def __getattr__(self, k):
        return getattr(self.__dict__["_base"], k)


def _insert_ranked(rows, row, q, cap):
    """`rows` with `row` put where its count ranks it (after the rows it ties with), cut to `cap` rows when the list
    is a capped ranking; the list is new (the caller's stays as it was)."""
    least = getattr(q, "order", "most") == "least" if q is not None else False
    out = list(rows)
    at = len(out)
    for k, r in enumerate(out):
        if (row["items"] < r["items"]) if least else (row["items"] > r["items"]):
            at = k
            break
    out.insert(at, row)
    if len(out) > cap:
        out = out[:cap]
    return out


def displays(view, idx):
    """{creator: display name} of the Instagram accounts whose export gives a name of their own (toolfix 7: a row
    named only by its handle, which an answer never prints; libview keeps the name as Item.display). A display name
    that is another creator's name, or a second account's display name too, is not used: the handle stays."""
    seen = {}
    for it in view.items.values():
        d = getattr(it, "display", None)
        if d and it.creator and it.creator.startswith("@"):
            seen.setdefault(it.creator, d)
    taken = {Hm._squash(c) for c in idx.creators}
    counts = Counter(Hm._squash(d) for d in seen.values())
    return {c: d for c, d in seen.items() if Hm._squash(d) not in taken and counts[Hm._squash(d)] == 1}


def channel_names(view, idx, out):
    """Toolfix 7: every channel row of the sheet (a ranking, a theme's or an area's channels, new and stopped ones)
    that is an Instagram account keeps its handle as `handle` and is named by its display name when it has one."""
    ig = {c for c in idx.creators if c.startswith("@")}
    if not ig:
        return
    disp = displays(view, idx)

    def walk(o, key=None, top=False):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, k, top)
        elif isinstance(o, list):
            for row in o:
                if isinstance(row, dict):
                    nm = row.get("name")
                    if key == "channels" and isinstance(nm, str) and nm in ig and (top or disp.get(nm)):
                        # a ranking's own rows always (the name may be the handle itself); a row inside another
                        # row only when its name changed, so the results do not grow for nothing
                        row["handle"] = nm[1:]
                        if disp.get(nm):
                            row["name"] = disp[nm]
                    walk(row, None, False)

    def walk_top(o):
        for k, v in o.items():
            if k == "channels" and isinstance(v, list):
                walk(v, "channels", True)
            elif isinstance(v, dict) and k in ("new", "stopped"):
                walk(v, None, True)
            else:
                walk(v, k, False)
    walk_top(out)


UNLOCKED_THEME_ID = 10 ** 6   # the unlocked topic's theme row: an id no build gives a theme
# the unlocked topic's rows are named by this label (the topic word is the row's `topic`): a sentence that names a
# sensitive word through a row is refused by insight's own check, which does not know the turn's unlock (mvp22)
UNLOCKED_NAME = "the topic you asked about"


def _unlocked_rows(out, sc, prev, view, idx, facts, th, unlock, q):
    """Toolfix 1 (held-out I02.0: 2024 with dating unlocked counted 58 videos, Heart Notes 50 of them, and "the top
    theme was Home cooking with 8"): a sensitive theme keeps no name nor category in its build, so the items of a
    topic their message unlocked were in the totals and the channel rows but in no theme row and no area row. Here
    they are: one theme row (the topic's items no named theme row holds) and one area row (the topic's items no area
    holds), both named UNLOCKED_NAME with code's own topic word as `topic`, built by the same row builders, ranked
    where their counts put them, and marked `private: true`. A turn with no unlock never comes here."""
    import numpy as np
    if th is None or not len(sc.items):
        return
    topics = sensitive_items(view, idx, facts, None)[1]
    of = np.array([t == unlock for t in topics], dtype=bool)
    n_cap = getattr(q, "top", None)
    if (of & (facts.theme < 0))[sc.items].any():
        pid = UNLOCKED_THEME_ID
        theme = np.where(of & (facts.theme < 0), pid, -1).astype(np.int32)
        th_ = _Over(th, themes={pid: {"field": None, "mixed": False}}, fields={},
                    shown=lambda t: UNLOCKED_NAME if t == pid else th.shown(t), field_name=lambda f: None)
        rows_, _n = _theme_rows(view, sc, prev, _Over(facts, theme=theme), th_, q=q)
        if rows_:
            row = dict(rows_[0], area=UNLOCKED_NAME, topic=unlock, private=True, theme_id=None)
            out["themes"] = _insert_ranked(out.get("themes") or [], row, q, n_cap or THEMES_MAX)
            out["unthemed"] = int(out.get("unthemed", 0)) - int(row["items"])
            if "ranked" in out:
                out["ranked"]["themes"] += 1
    if (of & (facts.area < 0))[sc.items].any():
        area = np.where(of & (facts.area < 0), 0, -1).astype(np.int32)
        rows_ = _area_rows(sc, prev, _Over(facts, area=area, area_names=[UNLOCKED_NAME]), out.get("themes") or [],
                           q=q)
        if rows_:
            row = dict(rows_[0], topic=unlock, private=True)
            out["areas"] = _insert_ranked(out.get("areas") or [], row, q, n_cap or AREAS_MAX)
            if "ranked" in out:
                out["ranked"]["areas"] += 1


def _hidden_counts(idx, facts, hev, so, eo, rows, q):
    """What the hidden events of a scope hold: how many items, and whether a hidden entity would have ranked above the
    first row shown of each list (channels, themes, areas)."""
    import numpy as np
    m = hev.copy()
    if so is not None:
        m &= idx.day >= so
    if eo is not None:
        m &= idx.day <= eo
    items = np.unique(idx.it[m])
    out = {"sensitive": int(len(items)), "above": {}}
    least = getattr(q, "order", "most") == "least"
    th = facts.th
    groups = {"channels": Counter(int(c) for c in idx.creator[items] if c >= 0)}
    if th is not None:
        raw = Counter()
        for k in items.tolist():
            t = th.theme_id(idx.ids[k])
            if t is not None:
                raw[t] += 1
        groups["themes"] = raw
        topics = facts.__dict__.get("_sensitive", {}).get("all", (None, []))[1]
        groups["areas"] = Counter(topics[k] for k in items.tolist() if topics and topics[k])
    for name, cnt in groups.items():
        shown_rows = [r for r in rows.get(name) or [] if isinstance(r, dict) and isinstance(r.get("items"), int)]
        if not cnt:
            out["above"][name] = False
        elif not shown_rows:
            out["above"][name] = True
        elif least:
            out["above"][name] = min(cnt.values()) < shown_rows[0]["items"]
        else:
            out["above"][name] = max(cnt.values()) > shown_rows[0]["items"]
    return out


def _ids_from_events(idx, ev, so, eo, kind, n=10):
    """The items of the scope's events in the order a first, a last, a list or a top-items row reads them."""
    import numpy as np
    m = ev.copy()
    if so is not None:
        m &= idx.day >= so
    if eo is not None:
        m &= idx.day <= eo
    its, secs = idx.it[m].tolist(), idx.sec[m].tolist()
    if kind == "top_items":
        cnt = Counter(its)
        last = {}
        for p, t in zip(its, secs):
            last[p] = max(t, last.get(p, t))
        order = sorted(cnt, key=lambda p: (-cnt[p], -last[p], p))
        return [idx.ids[p] for p in order[:n]]
    seen = {}
    for t, p in sorted(zip(secs, its), reverse=(kind != "first")):
        seen.setdefault(p, t)
        if len(seen) >= n:
            break
    return [idx.ids[p] for p in seen]


class Scope:
    """The events in a window, after the question's filters, and their distinct items, with per-item counts."""

    def __init__(self, idx, facts, ev_mask, start_o, end_o):
        import numpy as np
        m = ev_mask.copy()
        if start_o is not None:
            m &= idx.day >= start_o
        if end_o is not None:
            m &= idx.day <= end_o
        self.ev = m
        self.ev_items = idx.it[m]
        self.ev_days = idx.day[m]
        self.items = np.unique(self.ev_items)
        self.idx, self.facts = idx, facts

    def totals(self):
        import numpy as np
        idx, f = self.idx, self.facts
        it = self.items
        yt = it[idx.platform[it] == 0]
        known = yt[f.length[yt] > 0]
        lo = known[f.short[known] == 0]
        med = {"long_median_min": int(round(float(np.median(f.length[lo])) / 60))} if len(lo) >= 5 else {}
        nsh, nlo = int((f.short[yt] == 1).sum()), int((f.short[yt] == 0).sum())
        # round 12, pass 2 fix: the Shorts share of the YouTube videos is the sheet's own number (said as a share,
        # never as a count: "Shorts made up 12,080 of your window")
        shs = {"shorts_share": _share(nsh, nsh + nlo)} if nsh + nlo else {}
        if nsh + nlo and len(yt):
            # round 12, pass 5 (the audit, (d): "79% of your YouTube videos" was of those with a known length; of all
            # of them it was 77%): the share said "of your YouTube videos" is of all of them (hidden from the writer)
            shs["shorts_yt_share"] = _share(nsh, len(yt))
        return {**med, **shs, "items": int(len(it)), "days_active": int(len(np.unique(self.ev_days))),
                "length_hours": _hours(f.length[known].sum()) if len(known) else 0.0,
                "length_known_share": _share(len(known), len(yt)),
                "shorts": int((f.short[yt] == 1).sum()), "long": int((f.short[yt] == 0).sum()),
                "over_3h": int((f.length[yt] == -2).sum()),
                "by_platform": {"youtube": int(len(yt)), "instagram": int(len(it) - len(yt))}}

    def per_item(self):
        """(events per item, latest day per item) over the scope, as arrays the size of the index."""
        import numpy as np
        n = len(self.idx.ids)
        cnt = np.bincount(self.ev_items, minlength=n)
        last = np.full(n, -1, dtype=np.int64)
        np.maximum.at(last, self.ev_items, self.ev_days)
        return cnt, last

    def days_by(self, key_of_item):
        """{key: distinct days} for a per-item key array (theme, creator), over the scope's events."""
        import numpy as np
        k = key_of_item[self.ev_items].astype(np.int64)
        sel = k >= 0
        pairs = np.unique(k[sel] * 10_000_000 + self.ev_days[sel].astype(np.int64))
        keys, counts = np.unique(pairs // 10_000_000, return_counts=True)
        return dict(zip(keys.tolist(), counts.tolist()))


def _length_by(it, key, facts, idx):
    """{key: (known length seconds, known YouTube items, Shorts among them)} for the items `it`."""
    import numpy as np
    k = key[it].astype(np.int64)
    ok = (k >= 0) & (idx.platform[it] == 0) & (facts.length[it] > 0)
    # round 12, pass 2 fix (judge B: a channel "46% Shorts" was 5 of 17, 29%): a video over 3 hours is left out of
    # the length sums, never out of a Shorts share (it is a long video); the share is over every video whose Short
    # status is known
    oks = (k >= 0) & (idx.platform[it] == 0) & (facts.short[it] >= 0)
    kk, ks = k[ok], k[oks]
    if not len(ks):
        return {}
    size = int(ks.max()) + 1
    secs = np.bincount(kk, weights=facts.length[it][ok].astype(np.float64), minlength=size)
    n = np.bincount(ks, minlength=size)
    sh = np.bincount(ks, weights=(facts.short[it][oks] == 1).astype(np.float64), minlength=size)
    return {j: (float(secs[j]), int(n[j]), int(sh[j])) for j in np.nonzero(n)[0].tolist()}


def _theme_rows(view, sc, prev, facts, th, q=None):
    """The themes of a scope, largest first, with their share against `prev` (a Scope or None)."""
    import numpy as np
    idx = sc.idx
    it = sc.items
    n = len(it)
    out = []
    if th is None or not n:
        return out, n
    tcount = Counter(facts.theme[it][facts.theme[it] >= 0].tolist())
    pcount = Counter(facts.theme[prev.items][facts.theme[prev.items] >= 0].tolist()) if prev is not None else Counter()
    pn = len(prev.items) if prev is not None else 0
    days = sc.days_by(facts.theme)
    lens = _length_by(it, facts.theme, facts, idx)
    yt = it[(idx.platform[it] == 0) & (facts.length[it] > 0)]
    total_secs = float(facts.length[yt].sum()) if len(yt) else 0.0
    cnt, last = sc.per_item()
    for tid, c in _ranked(tcount, q, THEMES_MAX):
        mem = it[facts.theme[it] == tid]
        chans = Counter(idx.creator[mem][idx.creator[mem] >= 0].tolist()).most_common(3)
        order = np.lexsort((-last[mem], -cnt[mem]))[:EXAMPLES]
        secs, known, shorts = lens.get(tid, (0.0, 0, 0))
        share = _share(c, n)
        row = {"name": th.shown(tid), "theme_id": int(tid), "field": th.field_name(th.themes[tid]["field"]),
               "items": int(c), "share": share, "days": int(days.get(tid, 0)), "length_hours": _hours(secs),
               "length_share": _share(secs, total_secs),
               "shorts_share": _share(shorts, known),
               "channels": [{"name": idx.creators[a], "items": int(b)} for a, b in chans],
               "examples": [idx.ids[int(mem[k])] for k in order], "mixed": bool(th.themes[tid].get("mixed")),
               "area": theme_area(th, tid)}
        if prev is not None:
            ps = _share(pcount.get(tid, 0), pn)
            row["previous_share"] = ps
            row["previous_items"] = int(pcount.get(tid, 0))
            row["change_vs_previous"] = round((share - ps) * 100, 1)   # percentage points
        out.append(row)
    return out, n - sum(tcount.values())


def _first_by_creator(idx, all_ev):
    """The first day each creator was watched (in the kinds and platforms asked), over the whole record."""
    import numpy as np
    big = np.iinfo(np.int64).max
    first = np.full(len(idx.creators) + 1, big, dtype=np.int64)
    cr = idx.creator[idx.it[all_ev]].astype(np.int64)
    sel = cr >= 0
    np.minimum.at(first, cr[sel], idx.day[all_ev][sel].astype(np.int64))
    return first, big


def _channel_rows(view, sc, idx, facts, th, all_ev, start_o, top=CHANNELS_MAX, first=None, prev=None, q=None):
    import numpy as np
    it = sc.items
    pc = Counter(idx.creator[prev.items][idx.creator[prev.items] >= 0].tolist()) if prev is not None else None
    c = Counter(idx.creator[it][idx.creator[it] >= 0].tolist())
    if not c:
        return []
    first, big = first or _first_by_creator(idx, all_ev)
    days = sc.days_by(idx.creator)
    lens = _length_by(it, idx.creator, facts, idx)
    out = []
    for cid, n in _ranked(c, q, top):
        mem = it[idx.creator[it] == cid]
        tc = Counter(facts.theme[mem][facts.theme[mem] >= 0].tolist())
        secs, known, shorts = lens.get(cid, (0.0, 0, 0))
        f = int(first[cid]) if first[cid] != big else None
        top_t = tc.most_common(1)[0][0] if tc else None
        extra = {"area": theme_area(th, top_t) if (th is not None and top_t is not None) else None,
                 "share": _share(n, len(it)), "theme_share": _share(tc.most_common(1)[0][1], n) if tc else 0.0}
        if pc is not None:
            extra["previous_items"] = int(pc.get(cid, 0))
        out.append({**extra, "name": idx.creators[cid], "items": int(n), "days": int(days.get(cid, 0)),
                    "length_hours": _hours(secs),
                    "theme": th.shown(tc.most_common(1)[0][0]) if (th is not None and tc) else None,
                    "shorts_share": _share(shorts, known),
                    "first_watched": _iso(f) if f is not None else None,
                    "new_in_window": bool(start_o is not None and f is not None and f >= start_o)})
    return out


def _when(idx, sc, base_ev=None):
    import numpy as np
    n = int(sc.ev.sum())
    if not n:
        return {}
    usual = {}
    if base_ev is not None and base_ev.any():   # round 12, pass 2 (T7): his own usual week, over his whole record
        wb = np.bincount(idx.wd[base_ev].astype(np.int64), minlength=7)
        usual = {"usual_weekday_share": _share(int(wb[:5].sum()), int(base_ev.sum()))}
    h = np.bincount(idx.hour[sc.ev].astype(np.int64), minlength=24)
    wd = np.bincount(idx.wd[sc.ev].astype(np.int64), minlength=7)
    top = sorted(range(24), key=lambda x: (-h[x], x))[:3]
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return {"busiest_hours": [{"hour": int(x), "share": _share(int(h[x]), n)} for x in top if h[x]],
            "weekday_share": _share(int(wd[:5].sum()), n), "weekend_share": _share(int(wd[5:].sum()), n),
            "busiest_weekday": days[int(np.argmax(wd))], "events": n, **usual}


def _new_stopped(sc, prev, idx, facts, th, all_ev, start_o):
    """Themes present in the window and absent in the equal window before (and the reverse), with a floor; channels
    first watched in the window, and channels of the window before not watched in it."""
    new = {"themes": [], "channels": []}
    stopped = {"themes": [], "channels": []}
    if prev is None or th is None:
        return new, stopped
    n, pn = len(sc.items), len(prev.items)
    if not n or not pn:
        return new, stopped
    tc = Counter(facts.theme[sc.items][facts.theme[sc.items] >= 0].tolist())
    pc = Counter(facts.theme[prev.items][facts.theme[prev.items] >= 0].tolist())
    for tid, c in tc.most_common():
        if c >= NEW_MIN_ITEMS and c / n >= NEW_MIN_SHARE and pc.get(tid, 0) / pn < ABSENT_RATIO * c / n \
                and pc.get(tid, 0) * 2 <= c and pc.get(tid, 0) <= NEW_PREV_MAX:
            # round 12, pass 2 fix (judge A: "<theme> grew sharply and became new" of a theme with 35 videos the
            # year before): a theme that was there before grew; it is "new" only with at most a handful before
            new["themes"].append({"name": th.shown(tid), "items": int(c), "previous_items": int(pc.get(tid, 0))})
    for tid, c in pc.most_common():
        if c >= NEW_MIN_ITEMS and c / pn >= NEW_MIN_SHARE and tc.get(tid, 0) / n < ABSENT_RATIO * c / pn \
                and tc.get(tid, 0) * 2 <= c and tc.get(tid, 0) <= NEW_PREV_MAX:
            stopped["themes"].append({"name": th.shown(tid), "previous_items": int(c), "items": int(tc.get(tid, 0))})
    if start_o is not None:
        first, big = _first_by_creator(idx, all_ev)
        days = sc.days_by(idx.creator)
        now_c = Counter(idx.creator[sc.items][idx.creator[sc.items] >= 0].tolist())
        for cid, c in now_c.most_common():
            if c < NEW_CHANNEL_MIN:
                break
            if first[cid] != big and first[cid] >= start_o and days.get(cid, 0) >= NEW_CHANNEL_DAYS:
                mem = sc.items[idx.creator[sc.items] == cid]
                tc = Counter(facts.theme[mem][facts.theme[mem] >= 0].tolist())
                new["channels"].append({"name": idx.creators[cid], "items": int(c),
                                        "theme": th.shown(tc.most_common(1)[0][0]) if tc else None})
                if len(new["channels"]) >= 5:
                    break
    now_c = Counter(idx.creator[sc.items][idx.creator[sc.items] >= 0].tolist())
    for cid, c in Counter(idx.creator[prev.items][idx.creator[prev.items] >= 0].tolist()).most_common(50):
        if c >= NEW_CHANNEL_MIN and not now_c.get(cid):
            stopped["channels"].append({"name": idx.creators[cid], "previous_items": int(c)})
    new["themes"], new["channels"] = new["themes"][:5], new["channels"][:5]
    stopped["themes"], stopped["channels"] = stopped["themes"][:5], stopped["channels"][:5]
    return new, stopped


def _periods(idx, facts, th, ev_mask, start_o, end_o, by=None):
    """[{label, items, themes: [{name, share}]}] per year (per month for a span under 18 months, or as asked)."""
    import numpy as np
    m = ev_mask.copy()
    if start_o is not None:
        m &= idx.day >= start_o
    if end_o is not None:
        m &= idx.day <= end_o
    if not m.any():
        return [], None
    days = idx.day[m]
    lo, hi = date.fromordinal(int(days.min())), date.fromordinal(int(days.max()))
    months = (hi.year - lo.year) * 12 + hi.month - lo.month + 1
    unit = by or ("month" if months < 18 else "year")
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    keys = []
    if unit == "year":
        for y in range(lo.year, hi.year + 1):
            keys.append((str(y), date(y, 1, 1).toordinal(), date(y, 12, 31).toordinal()))
    else:
        y, mo = lo.year, lo.month
        while (y, mo) <= (hi.year, hi.month):
            keys.append((f"{names[mo - 1]} {y}", date(y, mo, 1).toordinal(), Hm._month_end(y, mo).toordinal()))
            y, mo = (y, mo + 1) if mo < 12 else (y + 1, 1)
    out = []
    for label, a, b in keys:
        sel = m & (idx.day >= a) & (idx.day <= b)
        it = np.unique(idx.it[sel])
        row = {"label": label, "items": int(len(it)), "themes": []}
        if th is not None and len(it):
            tc = Counter(facts.theme[it][facts.theme[it] >= 0].tolist())
            row["themes"] = [{"name": th.shown(t), "share": _share(c, len(it))} for t, c in tc.most_common(4)]
            ac = Counter(facts.area[it][facts.area[it] >= 0].tolist())   # round 12, pass 2 (T4): eras by area
            row["areas"] = [{"name": facts.area_names[a], "share": _share(c, len(it))} for a, c in ac.most_common(3)]
            row["area_shares"] = {facts.area_names[a]: _share(c, len(it)) for a, c in ac.items()}   # all of them
        yt = it[(idx.platform[it] == 0) & (facts.short[it] >= 0)] if len(it) else it
        if len(yt) >= 20:
            row["shorts_share"] = _share(int((facts.short[yt] == 1).sum()), len(yt))
            yta = it[idx.platform[it] == 0]   # round 12, pass 5: of all the period's YouTube videos (as said)
            row["shorts_yt_share"] = _share(int((facts.short[yta] == 1).sum()), len(yta))
        out.append(row)
    return out, unit


def _saved_not_opened(view, idx, facts, th, tids, limit=10):   # round 12, merge: up to 10 ids, the list "yes" shows
    """What the person saved (a playlist, a save, a collection) and never opened, on each of the themes `tids`, on
    every platform. Round 12, pass 6, second round (the hand check, b4: "You saved and never opened 6 <theme>": 6 was
    the YouTube ones; by hand 371, 290 of them reels and 75 posts on Instagram): the count is of every platform, and
    the row says what it counts ("noun": "videos", "posts" or "posts and videos"; "youtube": the YouTube ones)."""
    import numpy as np
    if th is None or not tids:
        return []
    sm = idx.kind_mask(SAVED_KINDS)
    saved = np.unique(idx.it[sm])
    watched = np.unique(idx.it[idx.kind_mask(("watch", "view"))])
    cand = saved[~np.isin(saved, watched)]
    last = np.full(len(idx.ids), -1, dtype=np.int64)
    np.maximum.at(last, idx.it[sm], idx.day[sm])
    out = []
    for tid in tids:
        mem = cand[facts.theme[cand] == tid]
        if not len(mem):
            continue
        mem = mem[np.argsort(-last[mem], kind="stable")]
        posts = sum(1 for k in mem if idx.platform[int(k)] != 0 and
                    getattr(view.items.get(idx.ids[int(k)]), "media", None) not in ("reel", "video"))
        noun = "videos" if not posts else "posts" if posts == len(mem) else "posts and videos"
        out.append({"theme": th.shown(tid), "n": int(len(mem)), "youtube": int((idx.platform[mem] == 0).sum()),
                    "noun": noun, "examples": [idx.ids[int(k)] for k in mem[:limit]]})
    return out


def _item_rows(view, idx, facts, th, ids, rec, kinds, start, end, first=False):
    """The items' rows; "at" is the day an item was last opened (its first open for a first: round 12, pass 5)."""
    out = []
    for i in ids:
        it = view.items.get(i)
        if it is None:
            continue
        k = idx.pos.get(i)
        ds = [d for d, kk in rec.events.get(i, []) if kk in kinds and (start is None or d >= start)
              and (end is None or d <= end)]
        length = int(facts.raw_length[k]) if k is not None and facts.raw_length[k] > 0 else None
        at = (min(ds) if first else max(ds)) if ds else None
        out.append({"id": i, "title": Hm._title(it), "channel": it.creator, "at": at and at.isoformat(),
                    "length_s": length,
                    "is_short": (None if k is None or facts.short[k] < 0 else bool(facts.short[k])),
                    "theme": th.shown(int(facts.theme[k])) if (th is not None and k is not None and
                                                               facts.theme[k] >= 0) else None,
                    "platform": it.platform})
    return out


DAY_ITEMS_MAX = 60   # round 12, pass 6 (X16): a day's items on the sheet (the cards are chosen from them)
DAY_ALL = 10         # a day of this many items or fewer is shown whole (insight.SHOW["items"])


def _by_instant(items, idx, ev, eo, kind, sort=True, so=None):
    """Round 12, pass 6 (X1, the hand check: "the last minecraft video" named the one opened at 00:04, not the one at
    09:12 the same day): a first's or a last's items in the order of the instant of their first (or last) open, the
    newest first for a last and a day; each item's local time of that open as "at_time" ("9:12 am"). The sentence,
    the cards and the sheet read this one order."""
    import numpy as np
    if not items:
        return
    pos = [idx.pos.get(it.get("id")) for it in items]
    m = ev & np.isin(idx.it, [p for p in pos if p is not None])
    if eo is not None:
        m &= idx.day <= eo
    if so is not None:   # the brain's tools (step 1 fix): a scoped first of a window, from the window's start
        m &= idx.day >= so
    first_t, last_t = {}, {}
    for p, t in zip(idx.it[m].tolist(), idx.sec[m].tolist()):
        if p not in first_t or t < first_t[p]:
            first_t[p] = t
        if p not in last_t or t > last_t[p]:
            last_t[p] = t
    use = first_t if kind == "first" else last_t
    for it, p in zip(items, pos):
        t = use.get(p)
        if t is not None:
            d = datetime.fromtimestamp(t, idx.zone)
            if it.get("at") and d.date().isoformat() != it["at"]:
                continue   # an open outside the sheet's own events: the row keeps its day
            h = d.hour % 12 or 12
            it["at_time"] = f"{h}:{d.minute:02d} {'am' if d.hour < 12 else 'pm'}"
            it["_t"] = t
    if sort:   # a first and a day in the order they were opened; a last newest first
        items.sort(key=lambda it: (it.get("_t") is None, (it.get("_t") or 0) * (-1 if kind == "last" else 1)))
    for it in items:
        it.pop("_t", None)


# ================================================================ the window's words
def window_words(q, w, start, end, rec, plats, lang="en"):
    """The window as said back, already carrying where the export ends."""
    newest = max((rec.ends[p] for p in plats if p in rec.ends), default=None)
    if w.kind == "all":
        oldest = Hm._record_start(rec, plats, q)
        if oldest and newest:
            return f"all your history ({Hm.span_words(oldest, newest)}, where your export ends)", False
        return "all your history", False
    if w.kind == "lately" and end:
        return f"the 4 weeks up to {Hm.day_words(end)}, where your export ends", True
    base = Hm.window_words(w, start, end, lang, cap=False).rstrip(",")
    for lead in ("in the ", "in ", "on "):
        if base.startswith(lead) and not base.startswith("in the last"):
            base = ("the " if lead == "in the " else "") + base[len(lead):]
            break
    if base.startswith("in the last"):
        base = base[3:]
    if newest and end and end >= newest:
        if start and start <= newest:
            label = base.split(" (")[0]
            if w.kind in ("day",):
                return f"{base}, the last day of your export", True
            m_ = re.match(r"^(from .+?) to \d{1,2} [A-Za-z]+ \d{4}$", label)
            if m_:   # round 12, pass 5 (the audit: "From 1 January 2024 to 24 November 2026 up to 30 October 2026")
                return f"{m_.group(1)} to {Hm.day_words(newest)}, where your export ends", True
            return f"{label} up to {Hm.day_words(newest)}, where your export ends", True
    return base, False


# ================================================================ the sheet
def sheet(view, rec, q, today, tz, prof=None, text=None, hide_sensitive=False, unlock=None):
    """The fact sheet of `q` (a history.HistoryQuery), or None when the record has nothing in scope.

    The brain's tools (design/brain_v1/SPEC.md 8.4): `hide_sensitive` leaves out every item of a sensitive topic (a
    theme of a sensitive category, or an item whose own text profile.sensitive flags) except those of `unlock` (one
    topic, set by code from their message), and adds `hidden` (how many were left out, and whether one would have
    ranked above the first row shown) and `ranked` (how many rows each ranking had). Off, the sheet is as before."""
    import numpy as np
    t0 = time.monotonic()
    idx, facts = index(view, tz)
    th = facts.th
    plats = Hm._scope_platforms(q, view, rec)
    if not plats:
        return None
    if q.topic and not q.channel and len(q.topic) == 1 and q.kind != "compare_topics":
        ch = Hm.channel_of(view, q.topic[0])
        if ch and (q.channel_hint or not any(Hm.holds(view.items[i].caption or "", q.topic[0])
                                             for i in rec.events if view.items.get(i) is not None)):
            q = q.model_copy(update={"channel": ch, "topic": []})
    kinds = Hm.HOW_KINDS[q.how]
    pcodes = [0 if p == "youtube" else 1 for p in plats]
    base_ev = idx.kind_mask(kinds) & np.isin(idx.platform[idx.it], pcodes)
    base_all, hidm = base_ev, None
    if hide_sensitive:   # the brain's tools (8.4): the sensitive topics' events are not in scope, nor in its base
        hidm = sensitive_items(view, idx, facts, unlock)[0][idx.it]
        base_ev = base_ev & ~hidm
    scoped = bool(hide_sensitive or _scoped(q))
    ev_filters = []      # the event filters of the scope, kept to count the hidden events under the same filters
    kind = sheet_kind(q)
    out = {"question": text, "kind": kind, "filters": {"topic": q.topic[0] if q.topic and kind != "compare_topics"
                                                       else None, "without_shorts": _no_shorts(q),
                                                       "platform": q.platform, "channel": q.channel, "how": q.how}}
    start, end = Hm.resolve(q.window, rec, plats, today)
    newest = max((rec.ends[p] for p in plats if p in rec.ends), default=None)
    oldest = Hm._record_start(rec, plats, q)
    w = q.window
    if w.kind == "days" and newest and start and end and start <= newest < end:
        # round 12, pass 3 fix (both judges, "what have i been into the last 3 months": "the last 90 days up to 30
        # October" over 67 days): like "lately", the last N days the record holds
        n = (end - start).days
        w = w.model_copy(update={"start": newest - timedelta(days=n), "end": newest})
        start, end = w.start, w.end
    if newest and start and start > newest and q.kind not in ("first", "last"):
        out["cannot_see"] = {"reason": "after", "asked": Hm.window_noun(w, start, end), "export_ends": newest.isoformat()}
        w = Hm.shifted(w, start, end, newest)
        start, end = w.start, w.end
    if oldest and end and end < oldest:
        out["cannot_see"] = {"reason": "before", "asked": Hm.window_noun(w, start, end),
                             "history_starts": oldest.isoformat()}
        out["window"] = {"words": Hm.window_noun(w, start, end), "start": start and start.isoformat(),
                         "end": end.isoformat(), "clipped": True}
        return out
    words, clipped = window_words(q, w, start, end, rec, plats)
    if getattr(q, "season", None):
        words = q.season + (f" ({Hm.span_words(start, end)})" if start and end else "") + \
            (", where your export ends" if clipped else "")
    eff_end = min(end, newest) if (end and newest) else (end or newest)
    eff_start = start or oldest
    out["window"] = {"words": words, "start": eff_start and eff_start.isoformat(),
                     "end": eff_end and eff_end.isoformat(), "clipped": bool(clipped or (start and oldest and
                                                                                         start < oldest)),
                     "ends": {p: rec.ends[p].isoformat() for p in plats if p in rec.ends}}
    if start and oldest and start < oldest:
        out["window"]["history_starts"] = oldest.isoformat()
    # ---- the filters: a channel, a topic (its themes and its words), without Shorts
    ev = base_ev.copy()
    left_out = {}
    if q.channel:
        cid = idx.creators.index(q.channel) if q.channel in idx.creators else -2
        ev &= idx.creator[idx.it] == cid
        ev_filters.append(idx.creator[idx.it] == cid)
    topic_tids = []
    topic_mask = None
    if q.topic and kind != "compare_topics":
        topic_mask = np.zeros(len(idx.ids), bool)
        for ph in q.topic:
            m, tids, _n_theme, _n_words = topic_items(view, rec, idx, facts, ph)
            topic_mask |= m
            topic_tids += [t for t in tids if t not in topic_tids]
        out["filters"]["topic_themes"] = [th.shown(t) for t in topic_tids] if th is not None else []
    if _scoped(q):   # the brain's tools (11.3): only, exclude, short
        sm = scope_mask(view, idx, facts, q)[idx.it]
        ev &= sm
        ev_filters.append(sm)
    if _no_shorts(q):
        # round 12, pass 6 (X6, the hand check: "22% of your long videos" was of every YouTube video not known to be a
        # Short, 8% of them of no known length: 24% of the long ones): without Shorts is the videos KNOWN to be long,
        # the set its words name ("of your long videos"); a video of no known length may be a Short and is left out
        sh = facts.short != 0
        cut = ev & sh[idx.it]
        ev &= ~sh[idx.it]
        ev_filters.append(~sh[idx.it])
    so = eff_start.toordinal() if eff_start else None
    eo = eff_end.toordinal() if eff_end else None
    ev_other = None
    if getattr(q, "weekday", None) is not None:
        # round 12, pass 6, second round (the hand check, n02: "what do i usually watch on sundays"): that weekday over
        # the window, set against the other days of the week in the same window
        day_ = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"][q.weekday]
        out["filters"]["weekday"] = day_
        wdm = idx.wd == q.weekday
        ev_other = ev & ~wdm
        ev = ev & wdm
        ev_filters.append(wdm)
        out["window"]["words"] = f"on {day_}, over {out['window']['words']}"
    if _no_shorts(q):
        cut_w = cut & ((idx.day >= so) if so is not None else True) & ((idx.day <= eo) if eo is not None else True)
        left_out = {"shorts": int(len(np.unique(idx.it[cut_w & (idx.platform[idx.it] == 0) &
                                                        (facts.short[idx.it] == 1)]))),
                    "reels": int(len(np.unique(idx.it[cut_w & (idx.platform[idx.it] == 1)]))),
                    "unknown_length": int(len(np.unique(idx.it[cut_w & (idx.platform[idx.it] == 0) &
                                                               (facts.short[idx.it] == -1)])))}
        out["filters"]["left_out"] = left_out
    if topic_mask is not None and kind == "count":
        out["window_totals"] = Scope(idx, facts, ev, so, eo).totals()   # the count's "of N you watched then"
    ev_pre = ev.copy()   # round 12, pass 5: the other filters (without Shorts, a channel), the topic not yet applied
    if topic_mask is not None:
        ev = ev & topic_mask[idx.it]
        ev_filters.append(topic_mask[idx.it])
    sc = Scope(idx, facts, ev, so, eo)
    # the equal window just before (or the other window of a comparison)
    prev, prev_words, prev_clipped = None, None, False
    pbounds = None
    if ev_other is not None and kind != "changed":
        prev = Scope(idx, facts, ev_other & topic_mask[idx.it] if topic_mask is not None else ev_other, so, eo)
        prev_words = "on the other days of the week"
    elif q.kind == "compare" and q.window2:
        s2, e2 = Hm.resolve(q.window2, rec, plats, today)
        e2c = min(e2, newest) if (e2 and newest) else e2
        prev = Scope(idx, facts, ev, s2 and s2.toordinal(), e2c and e2c.toordinal())
        prev_words = window_words(q, q.window2, s2, e2, rec, plats)[0]
    elif so is not None and eo is not None and w.kind != "all" and kind != "changed":
        ps, pe, prev_words = before_window(w, date.fromordinal(so), date.fromordinal(eo))
        if oldest is None or pe >= oldest.toordinal():
            prev = Scope(idx, facts, ev, ps, pe)
            pbounds = (ps, pe)
            prev_clipped = bool(oldest and ps < oldest.toordinal())
    out["totals"] = sc.totals()
    if prev is not None:
        out["previous"] = dict(prev.totals(), words=prev_words, clipped=prev_clipped)
    if hide_sensitive and "instagram" in plats:
        # the brain's tools (toolfix 4): the Instagram reels and videos, the length filter's other half
        out["totals"]["reels"] = _reels(view, idx, facts, sc.items)
        if prev is not None:
            out["previous"]["reels"] = _reels(view, idx, facts, prev.items)
    rows, unthemed = _theme_rows(view, sc, prev, facts, th, q=q)
    out["themes"] = rows
    out["unthemed"] = int(unthemed)
    if th is not None and len(sc.items):
        fc = Counter(int(f) for f in facts.field[sc.items] if f >= 0)
        out["fields"] = [{"name": th.field_name(f), "items": int(c), "share": _share(c, len(sc.items))}
                         for f, c in fc.most_common(6) if th.field_name(f)]
    out["channels"] = _channel_rows(view, sc, idx, facts, th, base_ev, so, prev=prev, q=q)
    out["areas"] = _area_rows(sc, prev, facts, out["themes"], q=q)
    if scoped:   # the brain's tools: how many rows each ranking had (its `rows_total`), and what was left out
        out["ranked"] = {"themes": int(len(np.unique(facts.theme[sc.items][facts.theme[sc.items] >= 0]))),
                         "channels": int(len(np.unique(idx.creator[sc.items][idx.creator[sc.items] >= 0]))),
                         "areas": int(len(np.unique(facts.area[sc.items][facts.area[sc.items] >= 0])))}
    if hide_sensitive and unlock:
        _unlocked_rows(out, sc, prev, view, idx, facts, th, unlock, q)
    if hidm is not None:
        hev = base_all & hidm
        for f_ in ev_filters:
            hev = hev & f_
        out["hidden"] = _hidden_counts(idx, facts, hev, so, eo, out, q)
        # toolfix 8 (the count was of the whole library): the friends' posts left out of this window, base and scope
        out["hidden"]["friends"] = friends_in(view, tz, kinds, plats, so, eo, q)
    if kind == "channels":   # round 12, pass 2 (T11): what the ranking says: the area most of the top 5 are
        top5 = [c for c in out["channels"][:5] if c.get("area")]
        if top5:
            a, k = Counter(c["area"] for c in top5).most_common(1)[0]
            out["top_areas"] = {"area": a, "n": int(k), "of": len(out["channels"][:5])}
    out["when"] = _when(idx, sc, base_ev)
    season_ = bool(getattr(q, "season", None) or getattr(q.window, "label", None))
    short_window = so is not None and eo is not None and eo - so + 1 < 7
    out["new"], out["stopped"] = ({"themes": [], "channels": []}, {"themes": [], "channels": []}) if short_window \
        else _new_stopped(sc, prev, idx, facts, th, base_ev, so)
    if season_ and eo is not None and kind == "top":
        # round 12, pass 6 (X17, row 8: "what he did then and has not since"): each channel new then, with the videos
        # of it opened after the season, up to where the record ends
        for c in (out["new"] or {}).get("channels") or []:
            if isinstance(c, dict) and c.get("name") in idx.creators:
                cid = idx.creators.index(c["name"])
                # round 12, pass 6, second round (the hand check, b8: "12 more of the second": 9 of the 12 had been
                # opened in the summer too): the videos opened since, and of them the ones new since
                c["since_items"], c["since_new"] = _since_counts(idx, base_ev, eo, cid)
    # ---- by kind
    if kind == "changed" or q.kind == "timeline" or q.by or (kind == "count" and so is not None and eo is not None
                                                             and eo - so >= 45):
        # round 12, merge (seam a): a count over more than about six weeks gets its periods too, the chart W's
        # layout draws for a count ("how many minecraft videos this year": by month)
        out["periods"], unit = _periods(idx, facts, th, ev, so, eo, by=q.by)
        out["periods_unit"] = unit
        if kind == "changed":
            out["change"] = _change(out["periods"], th, idx, facts, ev, so, eo, unit)
            out["eras"] = _eras(out["periods"])   # round 12, pass 2 (T4): what each stretch of years mostly was
            out["areas_change"] = _area_change(out["periods"])
    if kind == "compare_topics":
        out["topics"] = [_topic_row(view, rec, idx, facts, th, ph, ev, so, eo) for ph in q.topic]
        if pbounds:   # round 12, pass 2 (T9): the same two topics in the span before
            prevs = [_topic_row(view, rec, idx, facts, th, ph, ev, *pbounds) for ph in q.topic]
            for r, pr in zip(out["topics"], prevs):
                r["previous_items"] = pr["items"]
            out["comparison"] = _compare(out["topics"], [pr["items"] for pr in prevs], q.lang)
        else:
            out["comparison"] = _compare(out["topics"], None, q.lang)
    elif q.topic and kind in ("count", "first", "last", "channels", "top"):
        # round 12, pass 5 (the audit: a "without Shorts" follow-up's topic row kept its Shorts, 8,005 against 1,875):
        # the topic's own row under the sheet's other filters
        out["topics"] = [_topic_row(view, rec, idx, facts, th, ph, ev_pre, so, eo) for ph in q.topic]
    if kind in ("day", "first", "last") or q.kind in ("list", "top_items"):
        try:
            _text, ids, _extra = Hm.answer(view, q, today, prof, rec, said_end=True, quiet=("friends", "range",
                                                                                            "refresh"))
        except Exception:  # noqa: BLE001 - the list is extra; the sheet stands without it
            ids = []
        if scoped and kind == "day":   # the brain's tools: the code reply's list knows nothing of the scope
            in_scope = set(sc.items.tolist())
            ids = [i for i in ids if idx.pos.get(i) in in_scope]
        elif scoped and q.kind in ("list", "top_items"):
            ids = _ids_from_events(idx, ev, so, eo, q.kind, n=q.offset + q.n)[q.offset:]
        if kind in ("first", "last") and (topic_mask is not None or scoped):
            # round 12, pass 5 (the audit: "You first opened a gaming video on 5 April 2020" where the sheet's own
            # topic, its themes and its words, holds one from 21 August 2019): a first or a last is of the sheet's
            # own scope, its items in the order of their first (or last) open
            d_, i_, t_ = idx.day[ev], idx.it[ev], idx.sec[ev]
            if eo is not None:
                d_, i_, t_ = d_[d_ <= eo], i_[d_ <= eo], t_[d_ <= eo]
            if scoped and so is not None:
                # the brain's tools, step 1 fix (the tools audit: the items tool's "oldest" of October listed the
                # oldest of all history): a scoped first reads from the window's start too
                d_, i_, t_ = d_[d_ >= so], i_[d_ >= so], t_[d_ >= so]
            seen_ = {}
            # the brain's tools page past the first 10 (offset + n); today's reads keep 10
            cap_ = max(10, int(getattr(q, "offset", 0) or 0) + int(q.n)) if scoped else 10
            # round 12, pass 6 (X1: items of one day were in the order of their ids): by the instant of the open
            for t1, i1 in sorted(zip(t_.tolist(), i_.tolist()), reverse=(kind == "last")):
                seen_.setdefault(i1, t1)
                if len(seen_) >= cap_:
                    break
            ids = [idx.ids[i1] for i1 in seen_]
        if kind == "day":
            # round 12, pass 6 (X16, the hand check: the overview named a channel whose card was behind "more"): every
            # item of the day is on the sheet (the code reply's list first, then the rest by the time of the open);
            # the model is shown the first SHOW["items"], the cards are chosen from all of them
            m_ = ev & ((idx.day >= so) if so is not None else True) & ((idx.day <= eo) if eo is not None else True)
            last_t = {}
            for p_, t_ in zip(idx.it[m_].tolist(), idx.sec[m_].tolist()):
                last_t[p_] = max(t_, last_t.get(p_, t_))
            have = set(ids)
            ids = list(ids) + [idx.ids[p_] for p_, _t in sorted(last_t.items(), key=lambda x: -x[1])
                               if idx.ids[p_] not in have][:DAY_ITEMS_MAX]
        # (the brain's tools, step 1 fix: a scoped first of a window says each item's first open in the window, not
        # its first open ever; today's reads are unchanged)
        win_first = scoped and kind == "first"
        out["items"] = _item_rows(view, idx, facts, th, ids, rec, kinds,
                                  eff_start if (kind == "day" or win_first) else None,
                                  eff_end if kind == "day" else None, first=(kind == "first"))
        if kind in ("first", "last", "day"):
            # a day of more items than the cards show keeps the code reply's order (its "more" pages on from it); a
            # day the cards show whole is in the order it was opened
            _by_instant(out["items"], idx, ev, eo, kind,
                        sort=(kind != "day" or len(out["items"]) <= DAY_ALL), so=so if win_first else None)
        if kind in ("first", "last") and q.topic:
            out["periods"], out["periods_unit"] = _periods(idx, facts, th, ev, None, eo, by="year")
    # things saved on the window's themes and never opened
    tids = topic_tids or [r["theme_id"] for r in rows[:3]]
    # round 12, fix (judges: a channels answer offered saved comedy, music against cooking a travel video): the saved
    # things are on what the answer is about, the themes of the top channels, or the two topics compared
    if kind == "channels" and not topic_tids:
        by_name = {r["name"]: r["theme_id"] for r in rows if r.get("name")}
        if th is not None:
            # round 12, pass 3 fix (judge A, row 2: no so-what on the channels he keeps coming back to): a top
            # channel's theme is found among all the themes, not only the window's biggest
            for t_ in th.themes:
                by_name.setdefault(th.shown(t_), t_)
        ct = [by_name[c["theme"]] for c in out["channels"][:5] if c.get("theme") in by_name]
        tids = list(dict.fromkeys(ct)) or tids
    elif kind == "compare_topics" and q.topic:
        ct = []
        for ph in q.topic:
            ct += [t for t in topic_items(view, rec, idx, facts, ph)[1] if t not in ct]
        tids = ct or tids
    out["library"] = {"saved_not_opened": _saved_not_opened(view, idx, facts, th, tids)}
    # ---- round 12, pass 2: the day against the person's usual day (T10); what comes back each year (T5)
    if kind == "day" and so is not None:
        out["usual"] = _usual_day(idx, facts, base_ev, so)
        t = out["totals"]
        if out["usual"] and (t.get("shorts", 0) + t.get("long", 0)):
            out["usual"]["day_shorts_share"] = _share(t["shorts"], t["shorts"] + t["long"])
            if (t.get("by_platform") or {}).get("youtube"):   # round 12, pass 5: "of the day's YouTube videos"
                out["usual"]["day_shorts_yt_share"] = _share(t["shorts"], t["by_platform"]["youtube"])
        first, big = _first_by_creator(idx, base_ev)
        # round 12, pass 6 (X19, the auditor: a day of 26 channels said "2 were new" where 5 were): the count is
        # over every channel of the day, not the sheet's top list; the names lead with the top list's, by count
        cr_ = idx.creator[sc.items]
        day_c = Counter(cr_[cr_ >= 0].tolist())
        fresh_ids = [cid for cid, _n in day_c.most_common()
                     if first[cid] != big and _iso(int(first[cid])) == eff_start.isoformat()]
        top_names = [c["name"] for c in out["channels"] if c.get("first_watched") == eff_start.isoformat()]
        names = top_names + [idx.creators[cid] for cid in fresh_ids if idx.creators[cid] not in top_names]
        out["new_today"] = {"channels": len(fresh_ids), "names": names[:3]}
    if getattr(q, "season", None) or (so is not None and eo is not None and eo - so <= 100 and kind == "top"
                                      and w.kind not in ("lately", "day")):
        try:
            out["seasonal"] = _seasonal(idx, facts, th, ev, so, eo, rows)
        except Exception:  # noqa: BLE001 - extra; the sheet stands without it
            out["seasonal"] = []
    if getattr(q.window, "label", None) and kind == "top" and so is not None and eo is not None and th is not None:
        try:   # round 12, pass 3 (U8, row 8): what set the season apart from the rest of its year
            out["distinct"] = _distinct(idx, facts, th, ev, so, eo, view)
        except Exception:  # noqa: BLE001 - extra; the sheet stands without it
            out["distinct"] = {}
    if kind == "top" and into_question(text) and so is not None and eo is not None and th is not None:
        # round 12, pass 4 (V2, row 8: asked what he was INTO, the answer led with how he watched): the themes of the
        # window at their highest share in any span of its length, and those new then (hidden from the writer:
        # code's lead says them)
        try:
            out["into"] = _peaks_new(idx, facts, th, ev, so, eo, rows, year=(w.kind == "year"))
        except Exception:  # noqa: BLE001 - extra; the sheet stands without it
            out["into"] = {"peaked": [], "new": []}
    out["so_what_candidates"] = _so_what_candidates(out, kind, q)
    out["offers"] = _offers(q, kind, out)
    out["built_s"] = round(time.monotonic() - t0, 3)
    out["versions"] = {"themes": (th.meta.get("version") if th is not None else None),
                       "themes_embedding": (th.meta.get("embedding_model") if th is not None else None),
                       "lengths": __import__("mvp.lengths", fromlist=["x"]).VERSION}
    if hide_sensitive:   # the brain's tools (toolfix 7): an Instagram row's handle apart, its display name shown
        channel_names(view, idx, out)
    return out


# ================================================================ round 12, pass 2: the broad picture and the so-what
AREAS_MAX = 5
LEARNING = {"education", "science", "math", "technology", "history", "diy and making", "DIY and making",
            "art and design"}
FUN = {"gaming", "comedy", "internet culture", "film and tv", "film and TV", "music", "sports"}
SAVED_MIN = 3          # T5: a so-what about saved things needs at least 3 of them (never "1 video and 1 video")
SHIFT_POINTS = 0.10    # T5: Shorts' share moved by at least 10 points against the span before
MOVE_MIN = 0.03        # U5: an area's share moved by at least 3 points against the weeks before


def _area_rows(sc, prev, facts, theme_rows, q=None):
    """T3: the areas of a scope, largest first: items, share of everything opened, the share before and its change
    (a FRACTION, as the writer reads it), and the themes inside each (from the scope's theme rows)."""
    it = sc.items
    n = len(it)
    if facts.th is None or not n:
        return []
    ac = Counter(facts.area[it][facts.area[it] >= 0].tolist())
    pn = len(prev.items) if prev is not None else 0
    pcnt = Counter(facts.area[prev.items][facts.area[prev.items] >= 0].tolist()) if pn else Counter()
    out = []
    for a, c in _ranked(ac, q, AREAS_MAX):
        name = facts.area_names[a]
        row = {"name": name, "items": int(c), "share": _share(c, n),
               "themes": [{"name": t["name"], "share": t["share"]} for t in theme_rows
                          if t.get("area") == name and t.get("name")][:3]}
        if pn:
            row["previous_share"] = _share(pcnt.get(a, 0), pn)
            row["change_vs_previous"] = round(row["share"] - row["previous_share"], 3)
        out.append(row)
    return out


def _eras(periods):
    rows = [p for p in periods if not p.get("sparse") and p.get("areas")]
    out = []
    for p in rows:
        a = p["areas"][0]
        if out and out[-1]["area"] == a["name"]:
            out[-1]["to"] = p["label"]
            out[-1]["shares"].append(a["share"])
        else:
            out.append({"from": p["label"], "to": p["label"], "area": a["name"], "shares": [a["share"]]})
    for e in out:
        sh = e.pop("shares")
        e["share"] = round(sum(sh) / len(sh), 3)
    return out


def _area_change(periods):
    """T4: the areas' shares in the first and the last full period: what he left behind (fell most), what arrived
    (rose most), each with its shares then and now (fractions)."""
    rows = [p for p in periods if not p.get("sparse") and p.get("areas")]
    if len(rows) < 2:
        return {}
    a = rows[0].get("area_shares") or {x["name"]: x["share"] for x in rows[0]["areas"]}
    b = rows[-1].get("area_shares") or {x["name"]: x["share"] for x in rows[-1]["areas"]}
    moves = [{"name": k, "from_share": a.get(k, 0.0), "to_share": b.get(k, 0.0),
              "change": round((b.get(k, 0.0) - a.get(k, 0.0)) * 100, 1)} for k in sorted(set(a) | set(b))]
    left = sorted((m for m in moves if m["change"] <= -3), key=lambda m: m["change"])[:2]
    arrived = sorted((m for m in moves if m["change"] >= 3), key=lambda m: -m["change"])[:2]
    # round 12, pass 5: the Shorts then and now as said, of all the period's YouTube videos
    sh = [(p["label"], p.get("shorts_yt_share", p["shorts_share"])) for p in rows
          if isinstance(p.get("shorts_share"), (int, float))]
    out = {"from": rows[0]["label"], "to": rows[-1]["label"], "left": left, "arrived": arrived}
    if len(sh) >= 2:
        out["shorts"] = {"from": sh[0][0], "from_share": sh[0][1], "to": sh[-1][0], "to_share": sh[-1][1]}
    return out


def _usual_day(idx, facts, base_ev, day_o, prev_days=90):
    """T10: the person's usual day over the 90 days before a day (days with anything opened): the median count, the
    median Shorts share and the busiest hour; and how the day compares."""
    import numpy as np
    m = base_ev & (idx.day >= day_o - prev_days) & (idx.day < day_o)
    if not m.any():
        return {}
    days = idx.day[m]
    per = []
    sh, sh_yt = [], []
    for d in np.unique(days):
        it = np.unique(idx.it[m & (idx.day == d)])
        per.append(len(it))
        yt = it[(idx.platform[it] == 0) & (facts.short[it] >= 0)]
        if len(yt):
            sh.append(float((facts.short[yt] == 1).mean()))
        yt_all = it[idx.platform[it] == 0]
        if len(yt_all):
            # round 12, pass 6 (X7: the day's "90% of the day's YouTube videos" against a usual day's share of the
            # known-length ones): the usual day's twin on the same base, of all its YouTube videos
            sh_yt.append(float((facts.short[yt_all] == 1).mean()))
    if len(per) < 5:
        return {}
    h = np.bincount(idx.hour[m].astype(np.int64), minlength=24)
    return {"days": int(len(per)), "median_items": int(np.median(per)),
            "shorts_share": round(float(np.median(sh)), 3) if sh else None, "busiest_hour": int(np.argmax(h)),
            **({"shorts_yt_share": round(float(np.median(sh_yt)), 3)} if sh_yt and sh else {})}


def _so_what_candidates(out, kind, q):
    """T5: things worth saying after the answer, each with its facts, proposed by code; the writer picks at most one.
    Ranked by code (the strongest first). None on a day's list; never for 1 or 2 saved clips."""
    c = []
    if kind == "day":
        return c
    themes = {t["name"]: t for t in out.get("themes") or [] if t.get("name")}
    stopped = {x.get("name") if isinstance(x, dict) else x for x in (out.get("stopped") or {}).get("themes") or []}
    for x in (out.get("library") or {}).get("saved_not_opened") or []:
        t = themes.get(x.get("theme"))
        # round 12, pass 6, second round: the count said is of every platform, but a saved so-what is proposed only
        # where YouTube videos were saved and never opened (as before; the founder's four judged answers keep their
        # shape)
        if (x.get("youtube", x.get("n")) or 0) < SAVED_MIN:
            continue
        if _clip_theme(x.get("theme"), t):
            continue   # round 12, pass 2 fix (judges: "you saved 4 <comedy theme>, open them?" is not worth saying)
        faded = x.get("theme") in stopped or (t is not None and isinstance(t.get("change_vs_previous"), (int, float))
                                              and t["change_vs_previous"] <= -1.0)
        c.append({"key": ("lapsed_saves:" if faded else "saved:") + str(x["theme"]),
                  "kind": "lapsed_saves" if faded else "saved", "theme": x["theme"], "n": int(x["n"]),
                  "noun": x.get("noun") or "videos",
                  **({"share": t["share"], "previous_share": t.get("previous_share")} if t is not None else {})})
    ts = [t for t in out.get("themes") or [] if isinstance(t.get("change_vs_previous"), (int, float))]
    learn = sorted((t for t in ts if t.get("area") in LEARNING and t["change_vs_previous"] <= -1.5),
                   key=lambda t: t["change_vs_previous"])
    fun = sorted((t for t in ts if t.get("area") in FUN and t["change_vs_previous"] >= 1.5),
                 key=lambda t: -t["change_vs_previous"])
    ac = out.get("areas_change") or {}
    if kind == "changed" and ac.get("left") and ac.get("arrived"):
        # round 12, pass 2 fix (judge A, row 7: the so-what "reopen saved <comedy theme>" is not worth saying on a
        # change): the learning side that gave way to entertainment, between the first and the last full year
        lf = next((x for x in ac["left"] if x.get("name") in LEARNING), None)
        gr = next((x for x in ac["arrived"] if x.get("name") in FUN), None)
        if lf and gr:
            c.append({"key": "learning_faded:" + lf["name"], "kind": "learning_faded", "faded": lf["name"],
                      "faded_from": lf["from_share"], "faded_to": lf["to_share"], "grew": gr["name"],
                      "grew_from": gr["from_share"], "grew_to": gr["to_share"], "from": ac.get("from"),
                      "to": ac.get("to")})
    if learn and fun and kind in ("top", "count", "channels"):
        a, b = learn[0], fun[0]
        c.append({"key": "learning_faded:" + a["name"], "kind": "learning_faded", "faded": a["name"],
                  "faded_from": a.get("previous_share"), "faded_to": a["share"], "grew": b["name"],
                  "grew_from": b.get("previous_share"), "grew_to": b["share"]})
    tot, prev = out.get("totals") or {}, out.get("previous") or {}
    if all(isinstance(x.get(k), int) for x in (tot, prev) for k in ("shorts", "long")) and             tot["shorts"] + tot["long"] >= 30 and prev["shorts"] + prev["long"] >= 30 and \
            kind not in ("changed", "compare_topics"):   # pass 2 fix: a comparison's totals are of everything
        a = tot["shorts"] / (tot["shorts"] + tot["long"])
        b = prev["shorts"] / (prev["shorts"] + prev["long"])
        # round 12, pass 5 (the audit: "Shorts went up to 94% of your <topic> videos" was of those with a known
        # length): the shares said are of all the YouTube videos ("of your YouTube videos", "... on YouTube")
        ya, yb = (tot.get("by_platform") or {}).get("youtube"), (prev.get("by_platform") or {}).get("youtube")
        if ya and yb:
            a, b = tot["shorts"] / ya, prev["shorts"] / yb
        if abs(a - b) >= SHIFT_POINTS:
            c.append({"key": "shorts_shift:" + ("up" if a > b else "down"), "kind": "shorts_shift",
                      "direction": "up" if a > b else "down", "share": round(a, 3), "previous_share": round(b, 3),
                      "previous_words": prev.get("words"),
                      # round 12, pass 2 fix (judge A, row 3: "Shorts went up to 61% of your YouTube videos" under a
                      # topic's count read as all of YouTube): a topic's sheet says whose videos they are
                      **({"topic": (out.get("filters") or {}).get("topic")}
                         if (out.get("filters") or {}).get("topic") else {})})
    w = out.get("window") or {}
    try:
        long_w = (date.fromisoformat(w["end"]) - date.fromisoformat(w["start"])).days > 400
    except (KeyError, TypeError, ValueError):
        long_w = True
    chans = out.get("channels") or []
    if chans and not long_w and kind in ("top", "channels") and isinstance(chans[0].get("previous_items"), int):
        c0 = chans[0]
        pn = (prev.get("items") or 0)
        if c0.get("share", 0) >= 0.05 and pn and c0["previous_items"] / pn < c0["share"] / 3:
            c.append({"key": "channel_rise:" + c0["name"], "kind": "channel_rise", "channel": c0["name"],
                      "items": c0["items"], "previous_items": c0["previous_items"], "share": c0.get("share")})
    for x in out.get("seasonal") or []:
        c.append(dict(x, key="seasonal:" + x["theme"], kind="seasonal"))
    if kind == "top" and prev and not getattr(getattr(q, "window", None), "label", None) and not long_w:
        # round 12, pass 3 (U5, row 1): for "the most lately" the so-what is what is changing: what grew and what
        # faded against the weeks before, said as something to notice (areas, a share moved by 3 points or more)
        ar = [x for x in out.get("areas") or [] if isinstance(x.get("change_vs_previous"), (int, float))
              and isinstance(x.get("previous_share"), (int, float))]
        up = max(ar, key=lambda x: x["change_vs_previous"], default=None)
        dn = min(ar, key=lambda x: x["change_vs_previous"], default=None)
        if up and dn and up["change_vs_previous"] >= MOVE_MIN and dn["change_vs_previous"] <= -MOVE_MIN:
            c.append({"key": "moving:" + up["name"], "kind": "moving", "grew": up["name"],
                      "grew_from": up["previous_share"], "grew_to": up["share"], "faded": dn["name"],
                      "faded_from": dn["previous_share"], "faded_to": dn["share"], "previous_words": prev.get("words")})
    if kind == "top" and (getattr(getattr(q, "window", None), "label", None) or getattr(q, "season", None)):
        # round 12, pass 6 (X17): a channel new in a past season that has all but gone since, as something to
        # notice, with the step code takes (its theme, "only <theme>")
        from . import profile as P_
        nc = [x for x in (out.get("new") or {}).get("channels") or [] if isinstance(x, dict) and
              isinstance(x.get("since_items"), int) and (x.get("items") or 0) >= 20 and x.get("theme") and
              x["since_items"] <= 0.1 * x["items"] and not P_.sensitive(str(x.get("name")) + " " + str(x["theme"]))]
        if nc:
            x = max(nc, key=lambda x: x["items"])
            c.append({"key": "then_not_since:" + x["name"], "kind": "then_not_since", "channel": x["name"],
                      "items": int(x["items"]), "since": int(x["since_items"]), "theme": x["theme"]})
    if kind in ("first", "last"):
        ps = [p for p in out.get("periods") or [] if p.get("items")]
        if len(ps) >= 2:
            last, peak = ps[-1], max(ps, key=lambda p: p["items"])
            how = "deeper" if peak is last else ("still" if last["items"] >= 0.5 * peak["items"] else "faded")
            # round 12, pass 6, second round (the hand check, n05a: a first's arc not said after another first's):
            # the key names its topic, so "never the same so-what twice in a row" is of the same topic only
            tp_ = str((out.get("filters") or {}).get("topic") or "")
            c.insert(0, {"key": "path:" + how + (":" + tp_ if tp_ else ""), "kind": "path", "how": how,
                         "last_label": last["label"],
                         "last_items": last["items"], "peak_label": peak["label"], "peak_items": peak["items"]})
    order = {"path": 0, "moving": 1, "lapsed_saves": 1, "learning_faded": 2, "then_not_since": 2, "channel_rise": 3,
             "seasonal": 4, "shorts_shift": 5, "saved": 6}
    # round 12, pass 2 fix: among saved things, a learning theme's first (a next step), then the most saved
    c.sort(key=lambda x: (order.get(x["kind"], 9),
                          0 if (themes.get(x.get("theme")) or {}).get("area") in LEARNING else 1, -(x.get("n") or 0)))
    return c[:4]


_CLIP_AREAS = {"comedy", "internet culture"}
_CLIP_WORDS = re.compile(r"\b(?:clips?|memes?|edits?|compilations?|moments|funny|viral|pranks?|shorts|reactions?)\b",
                         re.I)


def _clip_theme(name, row=None):
    """Round 12, pass 2 fix: a theme of clips (memes, edits, viral clips, comedy): saved ones are no so-what."""
    area = (row or {}).get("area") if isinstance(row, dict) else None
    return bool(area in _CLIP_AREAS or _CLIP_WORDS.search(str(name or "")))


def _seasonal(idx, facts, th, ev, start_o, end_o, theme_rows):
    """T5: a theme of the window he returns to in the same months every year: in at least 3 years its share in those
    months is at least 1.5 times its share over that whole year (and 3 items or more)."""
    import numpy as np
    if th is None or start_o is None or end_o is None or end_o - start_o > 100:
        return []
    a, b = date.fromordinal(start_o), date.fromordinal(end_o)
    months = set()
    d = a
    while d <= b:
        months.add(d.month)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    m_all = ev.copy()
    days = idx.day[m_all]
    if not len(days):
        return []
    mo = np.array([date.fromordinal(int(x)).month for x in range(int(days.min()), int(days.max()) + 1)])
    base = int(days.min())
    ev_month = mo[idx.day[m_all] - base]
    ev_year = np.array([date.fromordinal(int(x)).year for x in idx.day[m_all]]) if len(days) < 400000 else None
    if ev_year is None:
        return []
    items = idx.it[m_all]
    out = []
    for t in theme_rows[:5]:
        tid = t.get("theme_id")
        if tid is None:
            continue
        years = 0
        seen = 0
        for y in sorted(set(ev_year.tolist())):
            sel_y = ev_year == y
            it_y = np.unique(items[sel_y])
            it_s = np.unique(items[sel_y & np.isin(ev_month, list(months))])
            if len(it_s) < 20 or len(it_y) < 100:
                continue
            seen += 1
            s_in = float((facts.theme[it_s] == tid).mean())
            s_y = float((facts.theme[it_y] == tid).mean())
            if s_in >= 1.5 * s_y and (facts.theme[it_s] == tid).sum() >= 3 and s_y > 0:
                years += 1
        if years >= 3:
            out.append({"theme": t["name"], "years": years, "of_years": seen})
    return out[:1]


_INTO_Q = re.compile(r"\binto\b|\bback in\b|\bwatching back\b|\bmetido\b|\ben qu[eé] estaba\b", re.I)
_MOST_Q = re.compile(r"\bmost\b|\bm[aá]s\b", re.I)


def into_question(text):
    """Round 12, pass 4 (V2): "what was i into in the summer of 2023", "what was i watching back in 2021", "what have i
    been into the last 3 months": a question about WHAT he was into (never "the most", a ranking)."""
    t = str(text or "")
    return bool(_INTO_Q.search(t)) and not _MOST_Q.search(t)


PEAK_TILE_MIN = 100     # V2: a span of the window's length counts with at least this many videos opened
PEAK_TILES_MIN = 3      # and a theme "peaked then" only against at least 3 such spans
PEAK_LIFT = 1.5         # at its highest share of any span, and at least 1.5 times its median share of them
PEAK_NEXT = 1.1         # and at least 1.1 times its next highest (a peak a hair above another span is no peak)
PEAK_MIN_SHARE = 0.02   # a theme of at least 2% of the window
PEAK_MIN_ITEMS = 20     # and 20 videos
NEW_BEFORE_MAX = 0.05   # "new then": before the window, at most 5% of its videos in the window (or 2)


def _month_spans(lo, hi, months):
    """Round 12, pass 5: every span of `months` whole calendar months the record holds from `lo` to `hi` (ordinals),
    sliding by one month: [(first day, last day)], none past `hi`."""
    a0 = date.fromordinal(lo)
    y, m = a0.year, a0.month
    out = []
    while True:
        y1, m1 = y + (m - 1 + months - 1) // 12, (m - 1 + months - 1) % 12 + 1
        end = (date(y1 + (m1 == 12), m1 % 12 + 1, 1) - timedelta(days=1)).toordinal()
        if end > hi:
            break
        out.append((date(y, m, 1).toordinal(), end))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def span_months(so, eo, year=False):
    """Round 12, pass 5: how many months one span of the window's length is (a year 12; 90 days 3; 4 weeks 1)."""
    return 12 if year else max(1, round((eo - so + 1) / 30.4))


def _peaks_new(idx, facts, th, ev, so, eo, rows, year=False):
    """Round 12, pass 4 (V2): {"peaked": [{name, area, share, items, peak_share, next_share, spans}], "new": [{name,
    area, share, items, before}]} for the window's own top themes (the ones the writer is shown). "New then": before
    the window he opened at most 5% as many of it (or 2).
    Round 12, pass 5 (the audit, (a): "peaked then, at 5%, more than in any other three months" was true only against
    the calendar seasons; the three months starting a month earlier held 5.4%): "peaked then" is computed exactly as
    it is said: its share of the window is at least its share in EVERY span of the window's length the record holds,
    sliding by a month (whole calendar months; a span that holds the window, or is the window, is not another span;
    spans of at least 100 videos), at least 1.1 times its share in every such span apart from the window, and 1.5 times
    its median share of them."""
    import numpy as np
    days, items = idx.day[ev], idx.it[ev]
    if not len(days):
        return {"peaked": [], "new": []}
    lo, hi = int(days.min()), max(int(days.max()), int(eo))
    months = span_months(so, eo, year)
    nth = int(facts.theme.max()) + 1 if len(facts.theme) else 0
    shares, apart = [], []
    for a, b in _month_spans(lo, hi, months):
        if (a <= so and b >= eo) or (abs(a - so) <= 3 and abs(b - eo) <= 3):
            continue   # the window itself, or a span that holds it
        m = (days >= a) & (days <= b)
        u = np.unique(items[m])
        if len(u) < PEAK_TILE_MIN:
            continue
        t = facts.theme[u]
        sh = np.bincount(t[t >= 0], minlength=nth) / len(u)
        shares.append(sh)
        if b < so or a > eo:
            apart.append(sh)
    peaked, new = [], []
    w = np.unique(items[(days >= so) & (days <= eo)])
    wt = facts.theme[w] if len(w) else np.zeros(0, int)
    wsh = np.bincount(wt[wt >= 0], minlength=nth) / len(w) if len(w) else np.zeros(nth)
    before = np.unique(items[days < so])
    bc = np.bincount(facts.theme[before][facts.theme[before] >= 0], minlength=nth) if len(before) else np.zeros(nth)
    for r in rows[:THEMES_MAX]:
        tid = r.get("theme_id")
        if tid is None or not len(w) or r["share"] < PEAK_MIN_SHARE or r["items"] < PEAK_MIN_ITEMS:
            continue
        here = float(wsh[tid]) if tid < len(wsh) else 0.0
        others = [float(s[tid]) for s in shares]
        far = [float(s[tid]) for s in apart] or others
        if len(others) >= PEAK_TILES_MIN and here >= max(others) and here >= PEAK_NEXT * max(far) and \
                here >= PEAK_LIFT * float(np.median(others)):
            peaked.append({"name": r["name"], "area": r.get("area"), "share": r["share"], "items": r["items"],
                           "peak_share": r["share"], "next_share": round(max(others), 3), "spans": len(others) + 1,
                           "span_months": months})
        b_ = int(bc[tid]) if tid < len(bc) else 0
        if b_ <= max(2, NEW_BEFORE_MAX * r["items"]) and r["share"] >= 0.01:
            new.append({"name": r["name"], "area": r.get("area"), "share": r["share"], "items": r["items"],
                        "before": b_})
    return {"peaked": peaked[:3], "new": [x for x in new if x["name"] not in {p["name"] for p in peaked}][:2]}


DISTINCT_LIFT = 1.5      # U8: a theme of a season at least 1.5 times its share in the rest of that year
DISTINCT_MIN = 0.02      # at least 2% of the season
DISTINCT_POINTS = 0.015  # and at least 1.5 points above the rest of the year


def _distinct(idx, facts, th, ev, so, eo, view=None):
    """Round 12, pass 3 (U8, row 8: "say what made that season distinct against the year around it"): the themes whose
    share of the season is at least 1.5 times their share of the rest of the same year (2% of the season or more, 1.5
    points above it; on the real library no theme of a summer doubled), with both shares, and the words for the rest
    of the year; {} when none."""
    import numpy as np
    a, b = date.fromordinal(so), date.fromordinal(eo)
    ys, ye = date(a.year, 1, 1).toordinal(), date(a.year, 12, 31).toordinal()
    inside = Scope(idx, facts, ev, so, eo)
    year = Scope(idx, facts, ev, ys, ye)
    rest = np.setdiff1d(year.items, inside.items)
    n_in, n_rest = len(inside.items), len(rest)
    if n_in < 50 or n_rest < 100:
        return {}
    t_in = Counter(facts.theme[inside.items][facts.theme[inside.items] >= 0].tolist())
    t_rest = Counter(facts.theme[rest][facts.theme[rest] >= 0].tolist())
    rows = []
    for tid, c in t_in.items():
        s_in, s_rest = c / n_in, t_rest.get(tid, 0) / n_rest
        name = th.shown(tid)
        if name and s_in >= DISTINCT_MIN and s_in >= DISTINCT_LIFT * max(s_rest, 1e-9) and \
                s_in - s_rest >= DISTINCT_POINTS:
            rows.append({"name": name, "share": round(s_in, 3), "rest_share": round(s_rest, 3), "items": int(c),
                         "area": theme_area(th, tid)})
    rows.sort(key=lambda r: -(r["share"] - r["rest_share"]))
    if not rows:
        return {}
    return {"rest_words": f"the rest of {a.year}", "themes": rows[:3]}


def _compare(topics, prev_topics, lang="en"):
    """T9: which side is bigger and by how much, by code (the writer never works out a ratio or a gap), and the
    balance in the span before."""
    if len(topics) < 2:
        return {}
    a, b = topics[0], topics[1]
    big, small = (a, b) if a["items"] >= b["items"] else (b, a)
    out = {"more": big["name"], "less": small["name"], "difference": int(big["items"] - small["items"])}
    if small["items"]:
        r = big["items"] / small["items"]
        out["times"] = round(r, 1)
        out["ratio_words"] = ("about the same" if r < 1.15 else "a little more" if r < 1.5 else
                              f"about {round(r * 2) / 2:g} times as many" if r < 3 else
                              f"about {round(r)} times as many")
        if lang == "es":
            out["ratio_words"] = ("más o menos lo mismo" if r < 1.15 else "un poco más" if r < 1.5 else
                                  f"unas {round(r * 2) / 2:g} veces más".replace(".", ",") if r < 3 else
                                  f"unas {round(r)} veces más")
    if prev_topics and len(prev_topics) >= 2:
        pa, pb = prev_topics
        out["previous"] = {"a": pa, "b": pb}
        if pb and pa:
            pr = (pa / pb) if big is a else (pb / pa)
            r2 = big["items"] / small["items"] if small["items"] else None
            if r2:
                out["balance"] = "wider" if r2 > pr * 1.15 else "narrower" if r2 < pr / 1.15 else "about the same"
                # round 12, pass 2 fix (judges, row 5: the balance against last year was not said): the ratio then,
                # in words, by code
                out["previous_ratio_words"] = ("about the same" if pr < 1.15 else "a little more" if pr < 1.5 else
                                               f"about {round(pr * 2) / 2:g} times as many" if pr < 3 else
                                               f"about {round(pr)} times as many")
    return out


def _since_counts(idx, ev, eo, cid):
    """(videos of channel `cid` opened after day `eo`, those of them never opened up to `eo`), over the events `ev`."""
    import numpy as np
    mine = ev & (idx.creator[idx.it] == cid)
    after = np.unique(idx.it[mine & (idx.day > eo)])
    before = np.unique(idx.it[mine & (idx.day <= eo)])
    return int(len(after)), int((~np.isin(after, before)).sum())


def _main_theme(idx, facts, th, items, cid):
    """The theme most of a channel's `items` are on, or None."""
    if th is None:
        return None
    mem = items[idx.creator[items] == cid]
    tc = Counter(int(x) for x in facts.theme[mem] if x >= 0)
    return th.shown(tc.most_common(1)[0][0]) if tc else None


def _topic_row(view, rec, idx, facts, th, phrase, ev, so, eo):
    import numpy as np
    m, tids, n_theme, n_words = topic_items(view, rec, idx, facts, phrase)
    sc = Scope(idx, facts, ev & m[idx.it], so, eo)
    t = sc.totals()
    t_items = t["items"]
    row = {"name": phrase, "items": t["items"], "days": t["days_active"], "length_hours": t["length_hours"],
           "length_known_share": t["length_known_share"], "shorts": t["shorts"], "long": t["long"],
           **({"shorts_share": t["shorts_share"]} if "shorts_share" in t else {}),
           **({"shorts_yt_share": t["shorts_yt_share"]} if "shorts_yt_share" in t else {}),
           "themes": [th.shown(x) for x in tids] if th is not None else [],
           "matched_by": ("themes and words" if tids else "words"),
           # round 12, pass 2 (T9): what is inside the topic in the window, by count
           "top_themes": [{"name": th.shown(t), "items": int(n)} for t, n in
                          Counter(int(x) for x in facts.theme[sc.items] if x >= 0).most_common(2)
                          # round 12, pass 2 fix (judge A: a 2-video theme "inside cooking"): 5% of the side or more
                          if th.shown(t) and n >= max(3, 0.05 * t_items)] if th is not None else [],
           # round 12, pass 6, second round (the hand check, c06: "<A> and <B> were the biggest themes, with <ch1> and
           # <ch2> behind them": both channels were 95% a third theme): each channel with its own main theme in the
           # topic, so a sentence that sets it behind a theme can be checked
           "channels": [{"name": idx.creators[c], "items": int(n), "theme": _main_theme(idx, facts, th, sc.items, c)}
                        for c, n in Counter(int(x) for x in idx.creator[sc.items] if x >= 0).most_common(3)]}
    allm = ev & m[idx.it]
    if allm.any():
        row["first_watched"] = _iso(int(idx.day[allm].min()))
        row["last_watched"] = _iso(int(idx.day[allm].max()))
    return row


SPARSE_MIN = 50   # a period with fewer items is too thin to say what was watched in it (marked "sparse")


def _change(periods, th, idx, facts, ev, so, eo, unit):
    """From the first period with enough items to the last: the themes that rose and faded (percentage points), and
    each one's peak. A record that starts with a few stray items (4 videos in its first year) would otherwise make
    "100% to 4%" of one of them."""
    import numpy as np
    if th is None:
        return {}
    total = sum(p["items"] for p in periods)
    floor = max(SPARSE_MIN, int(0.01 * total))
    for p in periods:
        p["sparse"] = p["items"] < floor
    full = [k for k, p in enumerate(periods) if not p["sparse"]]
    if len(full) < 2:
        return {}
    i0, i1 = full[0], full[-1]
    allp = {}
    for k in full:
        a, b = _period_bounds(periods[k]["label"], unit)
        sel = ev & (idx.day >= a) & (idx.day <= b)
        it = np.unique(idx.it[sel])
        tc = Counter(facts.theme[it][facts.theme[it] >= 0].tolist())
        allp[k] = {th.shown(t): _share(c, len(it)) for t, c in tc.items()} if len(it) else {}
    names = set().union(*[set(x) for x in allp.values()])
    rows = []
    for n in names:
        a, b = allp[i0].get(n, 0.0), allp[i1].get(n, 0.0)
        peak = max(full, key=lambda k: allp[k].get(n, 0.0))
        rows.append({"name": n, "from_share": a, "to_share": b, "change": round((b - a) * 100, 1),
                     "peak_period": periods[peak]["label"], "peak_share": allp[peak].get(n, 0.0)})
    rising = sorted((r for r in rows if r["change"] >= 2.0), key=lambda r: (-r["change"], r["name"]))[:5]
    fading = sorted((r for r in rows if r["change"] <= -2.0), key=lambda r: (r["change"], r["name"]))[:5]
    first, last = periods[i0], periods[i1]
    return {"from": first["label"], "to": last["label"], "rising": rising, "fading": fading,
            "steady_top": [t["name"] for t in last["themes"][:3] if t["name"] in {x["name"] for x in first["themes"]}],
            "sparse_before": [p["label"] for p in periods[:i0]]}


def _period_bounds(label, unit):
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    if unit == "year":
        y = int(label)
        return date(y, 1, 1).toordinal(), date(y, 12, 31).toordinal()
    m, y = label.split()
    mo = names.index(m) + 1
    return date(int(y), mo, 1).toordinal(), Hm._month_end(int(y), mo).toordinal()


PREV_SEASON = {"spring": "winter", "summer": "spring", "fall": "summer", "autumn": "summer", "winter": "fall"}


def before_window(w, a, b):
    """(start ordinal, end ordinal, words) of the window just before [a, b], as a person would say it: the day before,
    the week before, the month before, the year before, the same part of last year for this year so far, the season
    before, else the same number of days before."""
    n = (b - a).days + 1
    if w.kind == "year" and a.month == 1 and a.day == 1:
        if b == date(a.year, 12, 31):
            return date(a.year - 1, 1, 1).toordinal(), date(a.year - 1, 12, 31).toordinal(), str(a.year - 1)
        try:
            pb = b.replace(year=b.year - 1)
        except ValueError:
            pb = b.replace(year=b.year - 1, day=28)
        return (date(a.year - 1, 1, 1).toordinal(), pb.toordinal(),
                f"the same part of {a.year - 1} ({Hm.span_words(date(a.year - 1, 1, 1), pb)})")
    if w.kind == "month" and a.day == 1:
        y, m = (a.year, a.month - 1) if a.month > 1 else (a.year - 1, 12)
        pa, last = date(y, m, 1), Hm._month_end(y, m)
        pb = last if b == Hm._month_end(a.year, a.month) else min(last, date(y, m, b.day))
        words = Hm.month_words(pa) if pb == last else f"the same days of {Hm.month_words(pa)} ({Hm.span_words(pa, pb)})"
        return pa.toordinal(), pb.toordinal(), words
    if w.label and w.kind == "range":
        name = w.label.split()[1] if len(w.label.split()) > 1 else ""
        pb = a - timedelta(days=1)
        y, m = (a.year, a.month - 3) if a.month > 3 else (a.year - 1, a.month + 9)
        pa = date(y, m, 1)
        prev = PREV_SEASON.get(name)
        words = (f"the {prev} before" if prev else "the 3 months before") + f" ({Hm.span_words(pa, pb)})"
        return pa.toordinal(), pb.toordinal(), words
    pa, pb = a - timedelta(days=n), a - timedelta(days=1)
    if n == 1:
        words = f"the day before ({Hm.day_words(pb)})"
    elif n == 7:
        words = f"the week before ({Hm.span_words(pa, pb)})"
    elif n == 28:
        words = f"the 4 weeks before ({Hm.span_words(pa, pb)})"
    else:
        words = f"the {n} days before ({Hm.span_words(pa, pb)})"
    return pa.toordinal(), pb.toordinal(), words


def _offers(q, kind, out):
    offers = []
    t = out.get("totals") or {}
    if not _no_shorts(q) and (t.get("shorts") or 0) > 0 and kind not in ("first", "last"):
        offers.append("without_shorts")
    # round 12, pass 2 (T11): a ranking of channels is narrowed by its broad areas ("only gaming"), not by a theme
    # round 12, pass 3 (U6): a top answer (or a change) leads with its areas: those are offered first, then its
    # themes; the layout says only the ones the answer showed
    rows_ = ((out.get("areas") or []) if kind == "channels" else
             ((out.get("areas") or [])[:2] + (out.get("themes") or [])[:2]) if kind in ("top", "changed") else
             (out.get("themes") or []))
    for r in rows_[:4] if kind in ("top", "changed") else rows_[:2]:
        if r.get("name") and not q.topic and "only_topic:" + r["name"] not in offers:
            offers.append("only_topic:" + r["name"])
    if kind not in ("day", "first", "last") and q.kind not in ("list", "on_day"):
        offers.append("show_videos")
    try:
        a = date.fromisoformat(out["window"]["start"])
        b = date.fromisoformat(out["window"]["end"])
        if (b - a).days > 45 and kind != "changed" and q.by != "month":
            offers.append("by_month")
    except (KeyError, TypeError, ValueError):
        pass
    if kind in ("channels", "count") and out.get("themes"):
        offers.append("by_theme")
    return offers


def build(bot, person, q, now, text=None, hide_sensitive=False, unlock=None):
    """The fact sheet of the history question `q` for `person`, or None. Code only: no model, no network.
    `hide_sensitive`, `unlock`: see sheet() (the brain's tools; off as before)."""
    try:
        h = person["handle"]
        tz = person.get("timezone") or "UTC"
        today = now.astimezone(ZoneInfo(tz)).date()
        view = bot.view(person["library"])
        rec = Hm.record(view, tz)
        from . import profile as P
        prof = P.get(bot.store, h)
    except Exception:  # noqa: BLE001 - no sheet: the writer is not called and today's answer stands
        return None
    if hide_sensitive:
        return sheet(view, rec, q, today, tz, prof, text=text, hide_sensitive=True, unlock=unlock)
    return sheet(view, rec, q, today, tz, prof, text=text)

