"""PROTOTYPE ONLY - round 8.3 shared code (LOG.md "Round 8.3 fixed parameters", rows Y8.3-FY, Y8.3-PC, Y8.3-TI).

Base B8.2 = P (prior-p1, c82_lib.PlatformPrior) on route-r1 (B8.1). Each arm changes one thing:
  YouTubeGate     Y8.3-FY (fy-v1): round 8.2's rf-v1 refine of the top 20 (same prompt, model, schema, reorder
                  rule), applied only to rewrite-routed typed searches whose P platform weight reads YouTube
                  (q_ig < 0.5). Responses are read from round 8.2's cache when the inputs (repeat, search, the
                  candidate ids in order) are identical; new calls are cached under cache/r8.3/.
  StrictPrior     Y8.3-PC (pc-v1): P with a tighter creator match. A creator name key (handle or display name,
                  normalised to [a-z0-9]) is eligible only if its source string has >= 2 words (and >= 5 chars
                  normalised, as P) or is one word of >= 6 chars. Match = a contiguous 1-4-token query n-gram whose
                  concatenation equals the whole key (as P). Everything else as P.
  TeIG            Y8.3-TI (ti-v1): round 7's te-v1c lists (te BM25 + te dense on 3-small query vectors) under
                  coverage-fair fusion, with only Instagram items rankable in them, on every typed search (both
                  paths). P's platform read is computed from the own-list fusion exactly as in P, then applied to
                  the te-fused scores.
Method side only: never opens evals/labels/. Never prints query or item text.
"""
import json
import os
import sys
import threading

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import c4_lib as L  # noqa: E402
import c5_lib as F  # noqa: E402
import c81_lib as R  # noqa: E402
import c82_lib as P  # noqa: E402
import yt_lib as Y  # noqa: E402
from corpus import DATA  # noqa: E402

FY_VERSION = "fy-v1"
PC_VERSION = "pc-v1"
TI_VERSION = "ti-v1"

# ---------------- Y8.3-FY: refine gated to YouTube reads ----------------
FY_Q_IG_MAX = 0.5  # refine iff q_ig < 0.5 (strict), fixed in LOG.md
CACHE_R82 = P.CACHE
CACHE_R83 = os.path.join(DATA, "cache", "r8.3", f"{P.REFINE_VERSION}.jsonl")


class Refiner83(P.Refiner):
    """rf-v1 unchanged; reads round 8.2's cache and this round's, writes new responses to this round's only."""

    def __init__(self, S, te_rows):
        self.S = S
        self.summary = {c: r["summary"] for c, r in te_rows.items() if r.get("summary")}
        self.cache, self.source = {}, {}
        for path, tag in ((CACHE_R82, "r8.2"), (CACHE_R83, "r8.3")):
            if os.path.exists(path):
                for line in open(path):
                    r = json.loads(line)
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
                self.source[key] = "r8.3"
                os.makedirs(os.path.dirname(CACHE_R83), exist_ok=True)
                with open(CACHE_R83, "a") as f:
                    f.write(json.dumps(r) + "\n")
        return self.reorder(order, top, friend, send, r), r


# ---------------- Y8.3-PC: strict creator match ----------------
PC_MIN_WORDS = 2  # a multi-word handle / name is eligible (with >= 5 chars normalised, as P)
PC_MIN_SINGLE_CHARS = 6  # a one-word handle / name needs >= 6 chars normalised


def pc_key(s):
    """(normalised key, eligible) for one handle or display name."""
    toks = R.TOK.findall(" ".join(str(s or "").lstrip("@").lower().split()).replace("_", " ").replace(".", " "))
    n = R.norm_key("".join(toks))
    if len(toks) >= PC_MIN_WORDS:
        return n, len(n) >= R.MIN_NAME_CHARS
    return n, len(toks) == 1 and len(n) >= PC_MIN_SINGLE_CHARS


class StrictPrior(P.PlatformPrior):
    """prior-p1 with pc-v1's eligible name keys; read() / apply() and every weight unchanged."""

    def __init__(self, S, router):
        super().__init__(S, router)
        by_name = {}
        n_dropped = 0
        for it in S.items:
            k = F.creator_key(it)
            if not k or k not in self.creator_n:
                continue
            pd = it["platform_data"]
            for s in (pd.get("owner_handle"), pd.get("owner_name")):
                n, ok = pc_key(s)
                if ok:
                    by_name.setdefault(n, set()).add(k)
                elif len(n) >= R.MIN_NAME_CHARS:
                    n_dropped += 1
        self.by_name_p1 = self.by_name
        self.by_name = {n: sorted(v) for n, v in by_name.items()}
        self.n_keys = {"p1": len(self.by_name_p1), "pc": len(self.by_name), "name_strings_dropped": n_dropped}


# ---------------- Y8.3-TI: te lists for Instagram items only ----------------
TE_QV_STORE = "c4_queries"  # 3-small 512 d query / phrase / HyDE vectors (round 7's H5b store)


class TeIG:
    def __init__(self, S):
        ig = {c for it, c in zip(S.items, S.codes) if it["platform"] == "instagram"}
        self.E = L.EnrichIdx(L.te_sources(), set(S.pos), ig)
        f0 = L.EnrichIdx(L.te_sources(), set(S.pos), F.te_active_f0(S))
        self.same_as_f0 = self.E.codeset == f0.codeset
        self.n_rankable, self.n_f0 = len(self.E.codes), len(f0.codes)
        self.QVs = L.QueryVecs(TE_QV_STORE)

    def missing(self, texts):
        return sorted({t for t in texts if t not in self.QVs.vec})

    def prefetch(self, texts, purpose="c83_te_query_vectors"):
        miss = self.missing(texts)
        if miss:
            from sklearn.preprocessing import normalize
            V = normalize(Y.embed_texts(miss, purpose, batch=500, workers=1))
            self.QVs.vec.update(zip(miss, V))
            ids = list(self.QVs.vec)
            L.save_store(self.QVs.path, ids, np.array([self.QVs.vec[s] for s in ids]))
        return len(miss)

    def small_qv(self, texts, caps):
        """3-small vectors of the same dense strings, with the HyDE blend as c5_lib.own_lists builds it."""
        miss = self.missing(texts + caps)
        assert not miss, f"{len(miss)} te query strings not prefetched"
        Qv = np.array([self.QVs.vec[t] for t in texts], dtype=np.float32)
        if caps:
            Hh = np.array([self.QVs.vec[t] for t in caps], dtype=np.float32)
            v = (1 - L.HYDE_ALPHA) * Qv[0] + L.HYDE_ALPHA * Hh.mean(0)
            Qv = np.vstack([Qv, (v / np.linalg.norm(v))[None, :]])
        return Qv

    def group(self, texts, caps, bq, keep):
        return ([self.E.bm25(bq, keep), self.E.dense(self.small_qv(texts, caps), keep)], self.E.codeset)
