"""PROTOTYPE ONLY - round 8.6 shared code (LOG.md "Round 8.6 fixed parameters", rows Y8.6-WP, Y8.6-FL).

Base B8.5 = Q8 (q8-v1: TFY with the per-dimension int8 3-large item store everywhere). Each arm changes one thing:
  WP   Y8.6-WP (wp-v1): YouTube interaction prior in fused-rank places, m(i) = min(5, 3 g_w + 2 like + 2 playlist),
       g_w = min(ln(1 + max(watch_count - 1, 0)) / ln 4, 1); key = position - m, stable; after P's multiplier,
       before the refine gate. Instagram items m = 0.
  FL   Y8.6-FL (fl-v1): YouTube items' shared-BM25 RRF term replaced by title-only (1.0) and channel-only (0.5)
       BM25 lists over YouTube items (tie-aware mean ranks); Instagram items keep their shared-BM25 rank.
       Coverage-fair te imputation uses n_O = 2 (Instagram) / 2.5 (YouTube).
In both arms q_ig is read from the B8.5 own-list fusion, so the prior multiplier and the refine gate equal B8.5's.
The refine (rf-v1) reads the round-8.2 ... 8.5 caches and writes new responses only under cache/r8.6/.
Method side only: never opens evals/labels/. Never prints query or item text. Reads no timestamp of any kind.
"""
import json
import math
import os
import sys
import threading

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import c4_lib as L  # noqa: E402
import c5_lib as F  # noqa: E402
import c82_lib as P  # noqa: E402
import c85_lib as X  # noqa: E402
import yt_lib as Y  # noqa: E402
from corpus import DATA, fix_ws  # noqa: E402

WP_VERSION, FL_VERSION = "wp-v1", "fl-v1"
WP_CAP = 5.0  # fused-rank places
WP_W_REWATCH, WP_W_LIKE, WP_W_PLAYLIST = 3.0, 2.0, 2.0
WP_REWATCH_SAT = 3  # rewatches at which g_w = 1
FL_W_TITLE, FL_W_CHANNEL = 1.0, 0.5
FL_N_O = {"ig": 2.0, "yt": 1.0 + FL_W_TITLE + FL_W_CHANNEL}
REFINE_Q_IG_MAX = X.REFINE_Q_IG_MAX
CACHE_R86 = os.path.join(DATA, "cache", "r8.6", f"{P.REFINE_VERSION}.jsonl")
CACHES = X.CACHES + ((CACHE_R86, "r8.6"),)


# ---------------- refine cache (rf-v1 unchanged) ----------------
class Refiner86(X.Refiner85):
    def __init__(self, S, te_rows):
        self.S = S
        self.summary = {c: r["summary"] for c, r in te_rows.items() if r.get("summary")}
        self.cache, self.source = {}, {}
        for path, tag in CACHES:
            if os.path.exists(path):
                for line in open(path):
                    r = json.loads(line)
                    if r["key"] not in self.cache:  # first (oldest) response with identical inputs wins
                        self.cache[r["key"]] = r
                        self.source[r["key"]] = tag
        self.lock = threading.Lock()

    def get(self, rep, qid, query, order, allow_call=False):
        top, friend, send = self.split_top(order)
        key = P.cache_key(rep, qid, send)
        r = self.cache.get(key)
        if r is None:
            if not allow_call:
                raise KeyError("refine response not cached (run `refine` first)")
            res = self.call(query, send) if send else {"ok": True, "ids": [], "tries": 0, "seconds": 0.0,
                                                         "cost_usd": 0.0, "in_tokens": 0, "out_tokens": 0}
            r = {"key": key, "rep": rep, "qid": qid, "n_sent": len(send), **res}
            with self.lock:
                self.cache[key] = r
                self.source[key] = "r8.6"
                os.makedirs(os.path.dirname(CACHE_R86), exist_ok=True)
                with open(CACHE_R86, "a") as f:
                    f.write(json.dumps(r) + "\n")
        return self.reorder(order, top, friend, send, r), r


# ---------------- Y8.6-WP: YouTube interaction prior ----------------
def wp_places(it):
    """Boost in fused-rank places from end-of-export counts and kinds only (no timestamps)."""
    if it["platform"] != "youtube":
        return 0.0
    pd = it["platform_data"]
    r = max(int(pd.get("watch_count") or 0) - 1, 0)
    g_w = min(math.log1p(r) / math.log1p(WP_REWATCH_SAT), 1.0)
    like = 1.0 if "like" in (it.get("interaction_kinds") or []) else 0.0
    pl = 1.0 if any(c != L.WATCH_LATER for c in (pd.get("collections") or [])) else 0.0
    return min(WP_CAP, WP_W_REWATCH * g_w + WP_W_LIKE * like + WP_W_PLAYLIST * pl)


class WP:
    def __init__(self, S):
        self.m = {}
        for it, c in zip(S.items, S.codes):
            v = wp_places(it)
            if v > 0:
                self.m[c] = v

    def apply(self, order):
        """key = position - m(i); stable by (key, position). Returns (order, n boosted in the top 20 before)."""
        keyed = sorted(range(len(order)), key=lambda p: (p - self.m.get(order[p], 0.0), p))
        n20 = sum(1 for c in order[:20] if c in self.m)
        return [order[p] for p in keyed], n20


# ---------------- Y8.6-FL: per-field YouTube keyword lists ----------------
class FieldBM25:
    """Y.BM25 over one field; rank() returns [(code, mean 1-based rank)] with equal scores sharing their mean rank,
    filters applied before ranking, tie groups starting within the first `depth` ranks entering whole."""

    def __init__(self, texts):
        self.bm = Y.BM25(texts)
        self.keys = self.bm.keys

    def rank(self, query, keep=None, depth=F.DEPTH):
        if not query.strip():
            return []
        s = self.bm.scores(query)
        idx = np.nonzero(s > 0)[0]
        if keep is not None:
            idx = np.array([n for n in idx if keep(self.keys[n])], dtype=np.int64)
        if len(idx) == 0:
            return []
        o = idx[np.argsort(-s[idx], kind="stable")]
        sv = s[o]
        out, start = [], 0
        while start < len(o) and start < depth:
            end = start + 1
            while end < len(o) and sv[end] == sv[start]:
                end += 1
            mean_rank = (start + 1 + end) / 2.0  # mean of 1-based ranks start+1 .. end
            out.extend((self.keys[n], mean_rank) for n in o[start:end])
            start = end
        return out


class FL:
    def __init__(self, S):
        title, chan = {}, {}
        self.group = {}
        for it, c in zip(S.items, S.codes):
            self.group[c] = "ig" if it["platform"] == "instagram" else "yt"
            if it["platform"] != "youtube":
                continue
            t = fix_ws(it.get("caption") or "").strip()
            ch = fix_ws(it["platform_data"].get("owner_name") or "").strip()
            if t:
                title[c] = t
            if ch:
                chan[c] = ch
        self.title, self.chan = FieldBM25(title), FieldBM25(chan)
        self.n_title, self.n_chan = len(title), len(chan)

    def fuse(self, dense, shared, bq, keep, group):
        """Fused (order, scores): dense RRF + [ig: shared-BM25 RRF | yt: 1.0 title + 0.5 channel RRF] + te group."""
        k = F.K_RRF
        so = {}
        for r, c in enumerate(dense[:F.DEPTH]):
            so[c] = so.get(c, 0.0) + 1.0 / (k + r + 1)
        for r, c in enumerate(shared[:F.DEPTH]):
            if self.group.get(c) == "ig":
                so[c] = so.get(c, 0.0) + 1.0 / (k + r + 1)
        tl = self.title.rank(bq, keep)
        cl = self.chan.rank(bq, keep)
        for c, mr in tl:
            so[c] = so.get(c, 0.0) + FL_W_TITLE / (k + mr)
        for c, mr in cl:
            so[c] = so.get(c, 0.0) + FL_W_CHANNEL / (k + mr)
        lists, e = group
        sg, ng = F._rrf_scores(lists), len(lists)
        out = {}
        for c, v in so.items():
            out[c] = v + (sg.get(c, 0.0) if (e is None or c in e) else v * ng / FL_N_O[self.group.get(c, "yt")])
        for c in sg:
            if c not in out:
                out[c] = sg[c]
        order = [c for c, _ in sorted(out.items(), key=lambda x: -x[1])]
        return order, out, {"title_len": len(tl), "channel_len": len(cl)}
