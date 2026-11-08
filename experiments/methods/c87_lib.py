"""PROTOTYPE ONLY - round 8.7 shared code (LOG.md "Round 8.7 fixed parameters", rows Y8.7-CI, Y8.7-R2).

Base B8.5 = Q8 (q8-v1: TFY with the per-dimension int8 3-large item store everywhere). Each arm changes one thing:
  CI   Y8.7-CI (ci-v1): a creator-level index (creators with >= 2 library items, mutual-follow creators excluded):
       one deterministic document per creator (display name, handle, handle split into words, top 10 hashtags,
       top 20 title / caption words), embedded once with 3-large 1,024 d (held as per-dimension int8) plus BM25.
       Per typed search: creators ranked by RRF(dense max over the search's own query rows, BM25 of its BM25
       string); the top 5 creators' gated, filter-kept member items ordered by the item's own dense score form one
       extra list, added to B8.5's fused score at 0.5 / (60 + r). No coverage-fair imputation.
  R2   Y8.7-R2 (route-r2): instant iff route-r1 instant OR (no '?' and no question word AND (<= 6 tokens OR a
       creator-name match at any length)).
q_ig is read from the search's own-list fusion exactly as in B8.5; in CI it is therefore identical to B8.5.
The refine (rf-v1) reads the round-8.2 ... 8.6 caches and writes new responses only under cache/r8.7/.
Method side only: never opens evals/labels/. Never prints query or item text. Reads no timestamp of any kind.
"""
import collections
import json
import os
import sys
import threading
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import c4_lib as L  # noqa: E402
import c5_lib as F  # noqa: E402
import c6_lib as G  # noqa: E402
import c7_lib as H  # noqa: E402
import c81_lib as R  # noqa: E402
import c82_lib as P  # noqa: E402
import c85_lib as X  # noqa: E402
import c86_lib as W  # noqa: E402
import yt_lib as Y  # noqa: E402
from common import GENERIC, STOP, strip_tags  # noqa: E402
from corpus import DATA, fix_ws  # noqa: E402

CI_VERSION, R2_VERSION = "ci-v1", "route-r2"
CI_MIN_ITEMS = 2
CI_K = 5  # top creators per search
CI_W = 0.5  # weight of the creator item list's RRF term
CI_N_TAGS, CI_N_WORDS = 10, 20
CI_STORE = os.path.join(L.EMB, "oai3l_1024_creators_ci1")
R2_MAX_SHORT = 6
REFINE_Q_IG_MAX = X.REFINE_Q_IG_MAX
CACHE_R87 = os.path.join(DATA, "cache", "r8.7", f"{P.REFINE_VERSION}.jsonl")
CACHES = W.CACHES + ((CACHE_R87, "r8.7"),)


# ---------------- refine cache (rf-v1 unchanged) ----------------
class Refiner87(X.Refiner85):
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
                self.source[key] = "r8.7"
                os.makedirs(os.path.dirname(CACHE_R87), exist_ok=True)
                with open(CACHE_R87, "a") as f:
                    f.write(json.dumps(r) + "\n")
        return self.reorder(order, top, friend, send, r), r


# ---------------- own lists, also returning the dense score array ----------------
def own_lists_s(S, qtexts, caps, bq, keep):
    """c5_lib.own_lists exactly (same arithmetic, same lists), plus the dense score array s and Qv."""
    Qv = S.QV.get(qtexts)
    if caps:
        Hh = S.QV.get(caps)
        v = (1 - L.HYDE_ALPHA) * Qv[0] + L.HYDE_ALPHA * Hh.mean(0)
        Qv = np.vstack([Qv, (v / np.linalg.norm(v))[None, :]])
    s = (S.V @ Qv.T).max(axis=1)
    sg = np.where(S.gate, s, -9.0)
    if keep is not None:
        sg = np.where(np.array([keep(c) for c in S.vcodes]), sg, -9.0)
    top = np.argsort(-sg)[:5]
    q2 = Qv.mean(0) + S.V[top].mean(0)
    q2 /= np.linalg.norm(q2)
    s = np.maximum(s, S.V @ q2)
    return [S._dense_rank(s, keep), S.bm.rank(bq, keep=keep) if bq.strip() else []], Qv, s


# ---------------- Y8.7-CI: creator-level index ----------------
def creator_docs(S):
    """{creator key: document text}, member lists and friend keys. Deterministic (sorted sets, (-count, term))."""
    members = collections.defaultdict(list)
    names, handles, friend = {}, {}, set()
    for it, c in zip(S.items, S.codes):  # corpus file order
        k = F.creator_key(it)
        if not k:
            continue
        members[k].append(c)
        pd = it["platform_data"]
        names.setdefault(k, F._clean(pd.get("owner_name")))
        handles.setdefault(k, F._clean(pd.get("owner_handle")).lstrip("@"))
        if (pd.get("owner_relation") or "") == "mutual":
            friend.add(k)
    keys = sorted(k for k, m in members.items() if len(m) >= CI_MIN_ITEMS and k not in friend)
    docs = {}
    for k in keys:
        tags, words = collections.Counter(), collections.Counter()
        for c in members[k]:
            it = S.items[S.pos[c]]
            for h in sorted({x.lower() for x in it["platform_data"].get("hashtags") or []}):
                if h not in GENERIC and len(h) >= 3:
                    tags[h] += 1
            words.update(sorted({t for t in H._W.findall(strip_tags(it.get("caption") or "").lower())
                                 if t not in STOP}))
        h = handles.get(k, "")
        docs[k] = fix_ws(" ".join([names.get(k, ""), h, L._ninja(h) if h else "",
                                   " ".join(R.top_terms(tags, CI_N_TAGS)), " ".join(R.top_terms(words, CI_N_WORDS))]))
    return docs, {k: members[k] for k in keys}, friend, {k: len(m) for k, m in members.items()}


def build_vectors(docs, purpose="c87_creator_embed"):
    """Embeds every document missing from the creator store (paid once); returns (ids, float32 unit rows)."""
    ids, V = L.load_store(CI_STORE)
    have = dict(zip(ids, V)) if len(ids) else {}
    miss = [k for k in sorted(docs) if k not in have]
    info = {"embedded_now": len(miss), "seconds": 0.0}
    if miss:
        t0 = time.time()
        Vm = G.embed_3l([docs[k] for k in miss], purpose, batch=500, workers=2)
        info["seconds"] = round(time.time() - t0, 1)
        have.update(zip(miss, Vm))
        ids = sorted(have)
        L.save_store(CI_STORE, ids, np.array([have[k] for k in ids], np.float32))
        meta = {"version": CI_VERSION, "model": f"{G.EMB3L_MODEL}@{G.EMB3L_DIM}", "n": len(ids),
                "note": "document texts are not stored; they are rebuilt deterministically from the corpus"}
        json.dump(meta, open(os.path.join(CI_STORE, "meta.json"), "w"))
    ids, V = L.load_store(CI_STORE)
    # load_store normalises the float16 rows (as every other store in these experiments)
    return ids, V, info


class CreatorIndex:
    def __init__(self, S, allow_embed=False):
        t0 = time.time()
        self.S = S
        docs, members, friend, n_items = creator_docs(S)
        self.keys = sorted(docs)
        self.idx = {k: n for n, k in enumerate(self.keys)}
        self.members = members
        self.n_friend_excluded = sum(1 for k in friend if n_items.get(k, 0) >= CI_MIN_ITEMS)
        self.doc_chars = [len(docs[k]) for k in self.keys]
        if allow_embed:
            ids, V, self.embed_info = build_vectors(docs)
        else:
            ids, V = L.load_store(CI_STORE)
            self.embed_info = {"embedded_now": 0, "seconds": 0.0}
        pos = {k: n for n, k in enumerate(ids)}
        assert all(k in pos for k in self.keys), "creator vectors missing: run `embed` first"
        Vf = np.array([V[pos[k]] for k in self.keys], np.float32)
        self.P = X.QMat(Vf)  # per-dimension int8, own scales
        self.bm = Y.BM25(docs)
        assert self.bm.keys == self.keys
        self.member_rows = {k: np.array([S.row_of[c] for c in m if c in S.row_of], np.int64) for k, m in members.items()}
        self.n_member_items = sum(len(m) for m in members.values())
        self.plat = {k: k.split(":", 1)[0] for k in self.keys}
        self.build_s = time.time() - t0

    def rank_creators(self, Qv, bq):
        lists = []
        s = (self.P @ Qv.T).max(axis=1)
        order = np.argsort(-s, kind="stable")[:F.DEPTH]  # ties -> creator key order (keys sorted)
        lists.append([self.keys[n] for n in order])
        if bq.strip():
            b = self.bm.scores(bq)
            b[b <= 0] = -np.inf
            o = np.lexsort((np.arange(len(b)), -b))
            lists.append([self.keys[n] for n in o[:F.DEPTH] if np.isfinite(b[n])])
        lists = [x for x in lists if x]
        return R.rrf_det(*lists, k=F.K_RRF, depth=F.DEPTH)[0]

    def item_list(self, top_creators, s, keep):
        S = self.S
        rows = [r for k in top_creators for r in self.member_rows[k].tolist()]
        rows = sorted(set(rows))
        rows = [r for r in rows if S.gate[r] and (keep is None or keep(S.vcodes[r]))]
        if not rows:
            return []
        ra = np.array(rows, np.int64)
        o = np.argsort(-s[ra], kind="stable")  # ties -> lower vector row
        return [S.vcodes[ra[n]] for n in o[:F.DEPTH]]

    def search(self, Qv, bq, s, keep):
        top = self.rank_creators(Qv, bq)[:CI_K]
        return top, self.item_list(top, s, keep)


def ci_fuse(order, sc, ci_list):
    """F_CI(i) = F_B8.5(i) + CI_W / (60 + r); insertion order B8.5's, then new items. Empty list -> unchanged."""
    if not ci_list:
        return order, sc
    out = dict(sc)
    for r, c in enumerate(ci_list[:F.DEPTH]):
        out[c] = out.get(c, 0.0) + CI_W / (F.K_RRF + r + 1)
    return [c for c, _ in sorted(out.items(), key=lambda x: -x[1])], out


# ---------------- Y8.7-R2: wider instant routing ----------------
class ShapeRouter2(R.ShapeRouter):
    """route-r2: route-r1 instant, OR no '?' / question word AND (<= 6 tokens OR creator-name match)."""

    def route(self, query):
        info = super().route(query)
        if info["path"] == "instant":
            info["r2"] = "r1"
            return info
        toks, m = R.markers(query)
        n = len(toks)
        info = {**info, "version": R2_VERSION}
        if not n or "qmark" in m or "question_word" in m:
            info["r2"] = "blocked"
            return info
        if n <= R2_MAX_SHORT:
            info["path"], info["reason"], info["r2"] = "instant", "r2_short", "short"
            return info
        if R.ShapeRouter.creator_match(self, toks):
            info["path"], info["reason"], info["r2"] = "instant", "r2_creator", "creator"
            info["creator_match"] = True
            return info
        info["r2"] = "long_unmatched"
        return info
