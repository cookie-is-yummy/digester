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
import threading
import time
from collections import Counter
from datetime import date, datetime
from zoneinfo import ZoneInfo

from . import history as Hm

KIND_OF = {"top_channels": "channels", "top_topics": "top", "top_items": "top", "count": "count", "list": "top",
           "on_day": "day", "first": "first", "last": "last", "timeline": "count", "compare": "compare_windows",
           "compare_topics": "compare_topics", "changed": "changed", "top": "top"}
THEMES_MAX, CHANNELS_MAX, EXAMPLES = 8, 10, 3
NEW_MIN_ITEMS, NEW_MIN_SHARE, ABSENT_SHARE = 5, 0.03, 0.005
NEW_CHANNEL_MIN, NEW_CHANNEL_DAYS = 5, 2
SAVED_KINDS = ("save", "collection", "share_self", "playlist")
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
        it_, day_, hour_, wd_, kind_ = [], [], [], [], []
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
                    d = d.astimezone(zone) if d.tzinfo else d
                    it_.append(k)
                    day_.append(d.toordinal())
                    hour_.append(d.hour)
                    wd_.append(d.weekday())
                    kind_.append(kc)
        self.it = np.array(it_, dtype=np.int32)
        self.day = np.array(day_, dtype=np.int32)
        self.hour = np.array(hour_, dtype=np.int8)
        self.wd = np.array(wd_, dtype=np.int8)
        self.kind = np.array(kind_, dtype=np.int8)
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
        self.short = np.full(n, -1, dtype=np.int8)
        for k, i in enumerate(idx.ids):
            it = view.items[i]
            if self.th is not None:
                t = self.th.theme_id(i)
                if t is not None and self.th.shown(t) is not None:
                    self.theme[k] = t
                f = self.th.field_id(i)
                if f is not None:
                    self.field[k] = f
            if it.platform == "youtube":
                ln, sh = L.length_of(it, rows)
                if ln:
                    self.length[k] = int(ln)
                    self.short[k] = 1 if sh else 0


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
    return round(a / b, 3) if b else 0.0


def topic_items(view, rec, idx, facts, phrase):
    """(item positions of a topic, how it was matched): the themes it maps to by code (themes.for_topic) plus every
    item whose own text holds its words."""
    import numpy as np
    from . import themes as T
    tids = T.for_topic(view, rec, phrase, facts.th) if facts.th is not None else []
    by_theme = np.isin(facts.theme, tids) if tids else np.zeros(len(idx.ids), bool)
    words = np.array([Hm.holds(view.items[i].caption or "", phrase) for i in idx.ids], dtype=bool)
    return by_theme | words, tids, int(by_theme.sum()), int(words.sum())


class Scope:
    """The events in a window, after the question's filters, and their distinct items."""

    def __init__(self, idx, facts, ev_mask, start_o, end_o):
        import numpy as np
        m = ev_mask.copy()
        if start_o is not None:
            m &= idx.day >= start_o
        if end_o is not None:
            m &= idx.day <= end_o
        self.ev = m
        self.items = np.unique(idx.it[m])
        self.idx, self.facts = idx, facts

    def totals(self):
        import numpy as np
        idx, f = self.idx, self.facts
        it = self.items
        yt = it[idx.platform[it] == 0]
        known = yt[f.length[yt] > 0]
        out = {"items": int(len(it)), "days_active": int(len(np.unique(idx.day[self.ev]))),
               "length_hours": _hours(f.length[known].sum()) if len(known) else 0.0,
               "length_known_share": _share(len(known), len(yt)),
               "shorts": int((f.short[yt] == 1).sum()), "long": int((f.short[yt] == 0).sum()),
               "by_platform": {"youtube": int(len(yt)), "instagram": int(len(it) - len(yt))}}
        return out


def _theme_rows(view, sc, prev, facts, th, rank_by_events=None):
    """The themes of a scope, largest first, with their share against `prev` (a Scope or None)."""
    import numpy as np
    idx = sc.idx
    it = sc.items
    n = len(it)
    out = []
    if th is None or not n:
        return out, n
    tcount = Counter(int(t) for t in facts.theme[it] if t >= 0)
    pcount = Counter(int(t) for t in facts.theme[prev.items] if t >= 0) if prev is not None else Counter()
    pn = len(prev.items) if prev is not None else 0
    ev_items = idx.it[sc.ev]
    ev_days = idx.day[sc.ev]
    for tid, c in tcount.most_common(THEMES_MAX):
        mem = it[facts.theme[it] == tid]
        mset = np.isin(ev_items, mem)
        yt = mem[idx.platform[mem] == 0]
        known = yt[facts.length[yt] > 0]
        chans = Counter(idx.creators[c2] for c2 in idx.creator[mem] if c2 >= 0).most_common(3)
        evc = Counter(int(x) for x in ev_items[mset])
        ex = sorted(mem, key=lambda k: (-evc.get(int(k), 0), -int(ev_days[mset][ev_items[mset] == k].max())))[:EXAMPLES]
        share = _share(c, n)
        row = {"name": th.shown(tid), "theme_id": tid, "field": th.field_name(th.themes[tid]["field"]),
               "items": int(c), "share": share, "days": int(len(np.unique(ev_days[mset]))),
               "length_hours": _hours(facts.length[known].sum()) if len(known) else 0.0,
               "shorts_share": _share(int((facts.short[known] == 1).sum()), len(known)),
               "channels": [{"name": a, "items": int(b)} for a, b in chans],
               "examples": [idx.ids[int(k)] for k in ex], "mixed": bool(th.themes[tid].get("mixed"))}
        if prev is not None:
            ps = _share(pcount.get(tid, 0), pn)
            row["previous_share"] = ps
            row["previous_items"] = int(pcount.get(tid, 0))
            row["change_vs_previous"] = round((share - ps) * 100, 1)   # percentage points
        out.append(row)
    return out, n - sum(tcount.values())


def _channel_rows(view, sc, idx, facts, th, all_ev, start_o, top=CHANNELS_MAX):
    import numpy as np
    it = sc.items
    c = Counter(int(x) for x in idx.creator[it] if x >= 0)
    first = {}
    if c:
        cr = idx.creator[idx.it[all_ev]]
        days = idx.day[all_ev]
        for cid in c:
            sel = cr == cid
            if sel.any():
                first[cid] = int(days[sel].min())
    ev_items, ev_days = idx.it[sc.ev], idx.day[sc.ev]
    out = []
    for cid, n in c.most_common(top):
        mem = it[idx.creator[it] == cid]
        yt = mem[idx.platform[mem] == 0]
        known = yt[facts.length[yt] > 0]
        tc = Counter(int(t) for t in facts.theme[mem] if t >= 0)
        sel = np.isin(ev_items, mem)
        out.append({"name": idx.creators[cid], "items": int(n), "days": int(len(np.unique(ev_days[sel]))),
                    "length_hours": _hours(facts.length[known].sum()) if len(known) else 0.0,
                    "theme": th.shown(tc.most_common(1)[0][0]) if (th is not None and tc) else None,
                    "shorts_share": _share(int((facts.short[known] == 1).sum()), len(known)),
                    "first_watched": _iso(first[cid]) if cid in first else None,
                    "new_in_window": bool(start_o is not None and cid in first and first[cid] >= start_o)})
    return out


def _when(idx, sc):
    import numpy as np
    n = int(sc.ev.sum())
    if not n:
        return {}
    h = np.bincount(idx.hour[sc.ev].astype(np.int64), minlength=24)
    wd = np.bincount(idx.wd[sc.ev].astype(np.int64), minlength=7)
    top = sorted(range(24), key=lambda x: (-h[x], x))[:3]
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return {"busiest_hours": [{"hour": int(x), "share": _share(int(h[x]), n)} for x in top if h[x]],
            "weekday_share": _share(int(wd[:5].sum()), n), "weekend_share": _share(int(wd[5:].sum()), n),
            "busiest_weekday": days[int(np.argmax(wd))], "events": n}


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
    tc = Counter(int(t) for t in facts.theme[sc.items] if t >= 0)
    pc = Counter(int(t) for t in facts.theme[prev.items] if t >= 0)
    for tid, c in tc.most_common():
        if c >= NEW_MIN_ITEMS and c / n >= NEW_MIN_SHARE and pc.get(tid, 0) / pn < ABSENT_SHARE:
            new["themes"].append({"name": th.shown(tid), "items": int(c), "previous_items": int(pc.get(tid, 0))})
    for tid, c in pc.most_common():
        if c >= NEW_MIN_ITEMS and c / pn >= NEW_MIN_SHARE and tc.get(tid, 0) / n < ABSENT_SHARE:
            stopped["themes"].append({"name": th.shown(tid), "previous_items": int(c), "items": int(tc.get(tid, 0))})
    for row in _channel_rows(None, sc, idx, facts, th, all_ev, start_o, top=200):
        if row["new_in_window"] and row["items"] >= NEW_CHANNEL_MIN and row["days"] >= NEW_CHANNEL_DAYS:
            new["channels"].append({"name": row["name"], "items": row["items"], "theme": row["theme"]})
    now_c = Counter(int(x) for x in idx.creator[sc.items] if x >= 0)
    for cid, c in Counter(int(x) for x in idx.creator[prev.items] if x >= 0).most_common(50):
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
            tc = Counter(int(t) for t in facts.theme[it] if t >= 0)
            row["themes"] = [{"name": th.shown(t), "share": _share(c, len(it))} for t, c in tc.most_common(4)]
        out.append(row)
    return out, unit


def _saved_not_opened(view, idx, facts, th, tids, limit=3):
    """YouTube videos the person saved (a playlist, a save) and never watched, on each of the themes `tids`."""
    import numpy as np
    if th is None or not tids:
        return []
    saved = np.unique(idx.it[idx.kind_mask(SAVED_KINDS)])
    watched = set(np.unique(idx.it[idx.kind_mask(("watch", "view"))]).tolist())
    cand = [int(k) for k in saved if int(k) not in watched and idx.platform[k] == 0]
    out = []
    for tid in tids:
        mem = [k for k in cand if facts.theme[k] == tid]
        if not mem:
            continue
        last = {k: int(idx.day[(idx.it == k)].max()) for k in mem}
        mem.sort(key=lambda k: -last[k])
        out.append({"theme": th.shown(tid), "n": len(mem), "examples": [idx.ids[k] for k in mem[:limit]]})
    return out


def _item_rows(view, idx, facts, th, ids, rec, kinds, start, end):
    out = []
    for i in ids:
        it = view.items.get(i)
        if it is None:
            continue
        k = idx.pos.get(i)
        ds = [d for d, kk in rec.events.get(i, []) if kk in kinds and (start is None or d >= start)
              and (end is None or d <= end)]
        length = int(facts.length[k]) if k is not None and facts.length[k] > 0 else None
        out.append({"id": i, "title": Hm._title(it), "channel": it.creator, "at": (max(ds) if ds else None) and
                    max(ds).isoformat(), "length_s": length,
                    "is_short": (None if k is None or facts.short[k] < 0 else bool(facts.short[k])),
                    "theme": th.shown(int(facts.theme[k])) if (th is not None and k is not None and
                                                               facts.theme[k] >= 0) else None,
                    "platform": it.platform})
    return out


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
            return f"{label} up to {Hm.day_words(newest)}, where your export ends", True
    return base, False


# ================================================================ the sheet
def sheet(view, rec, q, today, tz, prof=None, text=None):
    """The fact sheet of `q` (a history.HistoryQuery), or None when the record has nothing in scope."""
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
    kind = sheet_kind(q)
    out = {"question": text, "kind": kind, "filters": {"topic": q.topic[0] if q.topic and kind != "compare_topics"
                                                       else None, "without_shorts": bool(getattr(q, "without_shorts",
                                                                                                 False)),
                                                       "platform": q.platform, "channel": q.channel, "how": q.how}}
    start, end = Hm.resolve(q.window, rec, plats, today)
    newest = max((rec.ends[p] for p in plats if p in rec.ends), default=None)
    oldest = Hm._record_start(rec, plats, q)
    w = q.window
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
    topic_tids = []
    topic_mask = None
    if q.topic and kind != "compare_topics":
        topic_mask = np.zeros(len(idx.ids), bool)
        for ph in q.topic:
            m, tids, _n_theme, _n_words = topic_items(view, rec, idx, facts, ph)
            topic_mask |= m
            topic_tids += [t for t in tids if t not in topic_tids]
        out["filters"]["topic_themes"] = [th.shown(t) for t in topic_tids] if th is not None else []
    if getattr(q, "without_shorts", False):
        sh = (facts.short == 1) | (idx.platform == 1)
        cut = ev & sh[idx.it]
        left_out = {"shorts": int(len(np.unique(idx.it[cut & (idx.platform[idx.it] == 0)]))),
                    "reels": int(len(np.unique(idx.it[cut & (idx.platform[idx.it] == 1)])))}
        ev &= ~sh[idx.it]
        out["filters"]["left_out"] = left_out
    so = eff_start.toordinal() if eff_start else None
    eo = eff_end.toordinal() if eff_end else None
    if topic_mask is not None and kind == "count":
        out["window_totals"] = Scope(idx, facts, ev, so, eo).totals()   # the count's "of N you watched then"
    if topic_mask is not None:
        ev = ev & topic_mask[idx.it]
    sc = Scope(idx, facts, ev, so, eo)
    # the equal window just before (or the other window of a comparison)
    prev, prev_words, prev_clipped = None, None, False
    if q.kind == "compare" and q.window2:
        s2, e2 = Hm.resolve(q.window2, rec, plats, today)
        e2c = min(e2, newest) if (e2 and newest) else e2
        prev = Scope(idx, facts, ev, s2 and s2.toordinal(), e2c and e2c.toordinal())
        prev_words = window_words(q, q.window2, s2, e2, rec, plats)[0]
    elif so is not None and eo is not None and w.kind != "all" and kind != "changed":
        span = eo - so + 1
        ps, pe = so - span, so - 1
        if oldest is None or pe >= oldest.toordinal():
            prev = Scope(idx, facts, ev, ps, pe)
            prev_words = f"the {span} days before ({Hm.span_words(date.fromordinal(ps), date.fromordinal(pe))})"
            prev_clipped = bool(oldest and ps < oldest.toordinal())
    out["totals"] = sc.totals()
    if prev is not None:
        out["previous"] = dict(prev.totals(), words=prev_words, clipped=prev_clipped)
    rows, unthemed = _theme_rows(view, sc, prev, facts, th)
    out["themes"] = rows
    out["unthemed"] = int(unthemed)
    if th is not None and len(sc.items):
        fc = Counter(int(f) for f in facts.field[sc.items] if f >= 0)
        out["fields"] = [{"name": th.field_name(f), "items": int(c), "share": _share(c, len(sc.items))}
                         for f, c in fc.most_common(6) if th.field_name(f)]
    out["channels"] = _channel_rows(view, sc, idx, facts, th, base_ev, so)
    out["when"] = _when(idx, sc)
    out["new"], out["stopped"] = _new_stopped(sc, prev, idx, facts, th, base_ev, so)
    # ---- by kind
    if kind == "changed" or q.kind == "timeline" or q.by:
        out["periods"], unit = _periods(idx, facts, th, ev, so, eo, by=q.by)
        out["periods_unit"] = unit
        if kind == "changed":
            out["change"] = _change(out["periods"], th, idx, facts, ev, so, eo, unit)
    if kind == "compare_topics":
        out["topics"] = [_topic_row(view, rec, idx, facts, th, ph, ev, so, eo) for ph in q.topic]
    elif q.topic and kind in ("count", "first", "last", "channels", "top"):
        out["topics"] = [_topic_row(view, rec, idx, facts, th, ph, base_ev, so, eo) for ph in q.topic]
    if kind in ("day", "first", "last") or q.kind in ("list", "top_items"):
        try:
            _text, ids, _extra = Hm.answer(view, q, today, prof, rec, said_end=True, quiet=("friends", "range",
                                                                                            "refresh"))
        except Exception:  # noqa: BLE001 - the list is extra; the sheet stands without it
            ids = []
        out["items"] = _item_rows(view, idx, facts, th, ids, rec, kinds, eff_start if kind == "day" else None,
                                  eff_end if kind == "day" else None)
        if kind in ("first", "last") and q.topic:
            out["periods"], out["periods_unit"] = _periods(idx, facts, th, ev, None, eo, by="year")
    # things saved on the window's themes and never opened
    tids = topic_tids or [r["theme_id"] for r in rows[:3]]
    out["library"] = {"saved_not_opened": _saved_not_opened(view, idx, facts, th, tids)}
    out["offers"] = _offers(q, kind, out)
    out["built_s"] = round(time.monotonic() - t0, 3)
    out["versions"] = {"themes": (th.meta.get("version") if th is not None else None),
                       "themes_embedding": (th.meta.get("embedding_model") if th is not None else None),
                       "lengths": __import__("mvp.lengths", fromlist=["x"]).VERSION}
    return out


def _topic_row(view, rec, idx, facts, th, phrase, ev, so, eo):
    import numpy as np
    m, tids, n_theme, n_words = topic_items(view, rec, idx, facts, phrase)
    sc = Scope(idx, facts, ev & m[idx.it], so, eo)
    t = sc.totals()
    row = {"name": phrase, "items": t["items"], "days": t["days_active"], "length_hours": t["length_hours"],
           "length_known_share": t["length_known_share"], "shorts": t["shorts"], "long": t["long"],
           "themes": [th.shown(x) for x in tids] if th is not None else [],
           "matched_by": ("themes and words" if tids else "words"),
           "channels": [{"name": idx.creators[c], "items": int(n)} for c, n in
                        Counter(int(x) for x in idx.creator[sc.items] if x >= 0).most_common(3)]}
    allm = ev & m[idx.it]
    if allm.any():
        row["first_watched"] = _iso(int(idx.day[allm].min()))
        row["last_watched"] = _iso(int(idx.day[allm].max()))
    _ = np
    return row


def _change(periods, th, idx, facts, ev, so, eo, unit):
    """From the first period to the last: the themes that rose and faded (percentage points), and each one's peak."""
    if len(periods) < 2 or th is None:
        return {}
    import numpy as np
    first, last = periods[0], periods[-1]

    def shares(p):
        return {t["name"]: t["share"] for t in p["themes"]}
    # full theme shares per period (not just the top 4)
    allp = []
    for p in periods:
        a, b = _period_bounds(p["label"], unit)
        sel = ev & (idx.day >= a) & (idx.day <= b)
        it = np.unique(idx.it[sel])
        tc = Counter(int(t) for t in facts.theme[it] if t >= 0)
        allp.append({th.shown(t): _share(c, len(it)) for t, c in tc.items()} if len(it) else {})
    names = set().union(*[set(x) for x in allp])
    rows = []
    for n in names:
        a, b = allp[0].get(n, 0.0), allp[-1].get(n, 0.0)
        peak = max(range(len(allp)), key=lambda k: allp[k].get(n, 0.0))
        rows.append({"name": n, "from_share": a, "to_share": b, "change": round((b - a) * 100, 1),
                     "peak_period": periods[peak]["label"], "peak_share": allp[peak].get(n, 0.0)})
    rising = sorted((r for r in rows if r["change"] >= 2.0), key=lambda r: -r["change"])[:5]
    fading = sorted((r for r in rows if r["change"] <= -2.0), key=lambda r: r["change"])[:5]
    _ = shares
    return {"from": first["label"], "to": last["label"], "rising": rising, "fading": fading,
            "steady_top": [t["name"] for t in last["themes"][:3] if t["name"] in {x["name"] for x in first["themes"]}]}


def _period_bounds(label, unit):
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    if unit == "year":
        y = int(label)
        return date(y, 1, 1).toordinal(), date(y, 12, 31).toordinal()
    m, y = label.split()
    mo = names.index(m) + 1
    return date(int(y), mo, 1).toordinal(), Hm._month_end(int(y), mo).toordinal()


def _offers(q, kind, out):
    offers = []
    t = out.get("totals") or {}
    if not getattr(q, "without_shorts", False) and (t.get("shorts") or 0) > 0 and kind not in ("first", "last"):
        offers.append("without_shorts")
    for r in (out.get("themes") or [])[:2]:
        if r.get("name") and not q.topic:
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


def build(bot, person, q, now, text=None):
    """The fact sheet of the history question `q` for `person`, or None. Code only: no model, no network."""
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
    return sheet(view, rec, q, today, tz, prof, text=text)

