"""PROTOTYPE ONLY - round 8.5 shared code (LOG.md "Round 8.5 fixed parameters", rows Y8.5-TS, Y8.5-Q8, Y8.5-QB).

Base B8.4 = TFY (tfy-v1: TI + rf-v1 refine of TI's top 20 on rewrite-routed typed searches with q_ig < 0.5).
Each arm changes one thing:
  TS   Y8.5-TS (ts-v1): the coverage-fair te group term (real and imputed) is multiplied by
       w = clip((q_ig - 0.35) / (0.75 - 0.35), 0, 1). w = 1 is TI's fusion exactly, w = 0 is P's.
  Q8   Y8.5-Q8 (q8-v1): the 3-large item vectors as per-dimension symmetric int8 (max-abs / 127), score
       V8 . (s * q) in float32, no renormalisation, no rescoring, wherever item vectors are read (QMat).
  QB   Y8.5-QB (qb-v1): Q8 everywhere, but typed own dense lists use sign-binary Hamming top 400 per dense query
       row (gated, filter-kept), union, int8 rescoring, PRF on the rescored candidates (q2's own Hamming top 400
       joins), dense list = the union sorted by int8 score.
The refine (rf-v1) reads the round-8.2 / 8.3 / 8.4 / 8.5 caches and writes new responses only under cache/r8.5/.
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
import c82_lib as P  # noqa: E402
import c84_lib as Z  # noqa: E402
from corpus import DATA  # noqa: E402

TS_VERSION, Q8_VERSION, QB_VERSION = "ts-v1", "q8-v1", "qb-v1"
TS_A, TS_B = 0.35, 0.75  # fixed in LOG.md (from B8.4's per-split q_ig distributions)
REFINE_Q_IG_MAX = Z.TFY_Q_IG_MAX  # 0.5, strict
Q8_LEVELS = 127
Q8_BLOCK = 8192  # rows per int8 -> float32 upcast block
QB_K = 400  # Hamming candidates per dense query row (and for q2)
CACHE_R85 = os.path.join(DATA, "cache", "r8.5", f"{P.REFINE_VERSION}.jsonl")
CACHES = Z.CACHES + ((CACHE_R85, "r8.5"),)


# ---------------- refine cache (rf-v1 unchanged) ----------------
class Refiner85(Z.Refiner84):
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
                self.source[key] = "r8.5"
                os.makedirs(os.path.dirname(CACHE_R85), exist_ok=True)
                with open(CACHE_R85, "a") as f:
                    f.write(json.dumps(r) + "\n")
        return self.reorder(order, top, friend, send, r), r

    def cached(self, rep, qid, order):
        return P.cache_key(rep, qid, self.split_top(order)[2]) in self.cache


# ---------------- Y8.5-TS: te group weight from the platform read ----------------
def ts_weight(q_ig):
    return float(min(1.0, max(0.0, (q_ig - TS_A) / (TS_B - TS_A))))


def fuse_weighted(own, group, w):
    """F(i) = RRF_O(i) + w * G_te(i) (coverage-fair term, real or imputed). w = 1 / 0 call fair_fuse exactly."""
    if w >= 1.0:
        return F.fair_fuse(own, [group])
    if w <= 0.0:
        return F.fair_fuse(own, [])
    lists, e = group
    if not lists:
        return F.fair_fuse(own, [])
    so = F._rrf_scores(own)
    n_o = max(len(own), 1)
    sg, ng = F._rrf_scores(lists), len(lists)
    out = {}
    for c, v in so.items():
        out[c] = v + w * (sg.get(c, 0.0) if (e is None or c in e) else v * ng / n_o)
    for c in sg:
        if c not in out:
            out[c] = w * sg[c]
    order = [c for c, _ in sorted(out.items(), key=lambda x: -x[1])]
    return order, out


# ---------------- Y8.5-Q8: int8 item store ----------------
class QMat:
    """int8 item vectors with per-dimension scale. `@` = V8 . (s * x) in float32 (block upcast); indexing returns
    dequantised float32 rows (V8 * s). Stands in for Combined.V wherever the 3-large item vectors are read."""

    def __init__(self, V):
        V = np.asarray(V, np.float32)
        self.s = (np.abs(V).max(axis=0) / Q8_LEVELS).astype(np.float32)
        self.s[self.s == 0] = 1.0
        self.q = np.clip(np.rint(V / self.s), -Q8_LEVELS, Q8_LEVELS).astype(np.int8)
        self.shape = self.q.shape
        self.dtype = np.dtype(np.float32)

    def __len__(self):
        return self.shape[0]

    def __getitem__(self, idx):
        return self.q[idx].astype(np.float32) * self.s

    def rows_dot(self, rows, X):
        """Scores of the given rows only (int8 upcast), X (d,) or (d, m)."""
        X = np.asarray(X, np.float32)
        Xs = X * self.s if X.ndim == 1 else X * self.s[:, None]
        return self.q[rows].astype(np.float32) @ Xs

    def __matmul__(self, X):
        X = np.asarray(X, np.float32)
        Xs = X * self.s if X.ndim == 1 else X * self.s[:, None]
        n = self.shape[0]
        out = np.empty((n,) if X.ndim == 1 else (n, X.shape[1]), np.float32)
        for i in range(0, n, Q8_BLOCK):
            out[i:i + Q8_BLOCK] = self.q[i:i + Q8_BLOCK].astype(np.float32) @ Xs
        return out

    def nbytes(self):
        return int(self.q.nbytes + self.s.nbytes)


# ---------------- Y8.5-QB: binary candidates + int8 rescoring ----------------
class BinIdx:
    def __init__(self, V):
        b = np.packbits(np.asarray(V) > 0, axis=1)  # (n, 128) uint8
        self.b8 = b
        self.b64 = np.ascontiguousarray(b).view(np.uint64)  # (n, 16)
        self.n = b.shape[0]
        self.rowid = np.arange(self.n, dtype=np.int64)

    def nbytes(self):
        return int(self.b8.nbytes)

    def code(self, x):
        return np.packbits(np.asarray(x) > 0).view(np.uint64)

    def hamming(self, x):
        return np.bitwise_count(self.b64 ^ self.code(x)).sum(axis=1, dtype=np.int64)

    def topk(self, x, elig, k=QB_K):
        """Rows of the k eligible items with the smallest Hamming distance; ties by lower row (unique keys)."""
        key = self.hamming(x) * self.n + self.rowid
        key = np.where(elig, key, np.iinfo(np.int64).max)
        m = min(k, int(elig.sum()))
        if m <= 0:
            return np.empty(0, np.int64)
        return np.sort(np.argpartition(key, m - 1)[:m])


def own_lists_qb(S, B, qtexts, caps, bq, keep):
    """c5_lib.own_lists with the dense full scan replaced by binary candidates + int8 rescoring (S.V is a QMat).
    Returns ([dense, bm25], Qv, candidate rows)."""
    Qv = S.QV.get(qtexts)
    if caps:
        H = S.QV.get(caps)
        v = (1 - L.HYDE_ALPHA) * Qv[0] + L.HYDE_ALPHA * H.mean(0)
        Qv = np.vstack([Qv, (v / np.linalg.norm(v))[None, :]])
    elig = S.gate if keep is None else (S.gate & np.array([keep(c) for c in S.vcodes]))
    cand = np.unique(np.concatenate([B.topk(x, elig) for x in Qv]))
    s1 = S.V.rows_dot(cand, Qv.T).max(axis=1)
    top = cand[np.argsort(-s1, kind="stable")[:5]]
    q2 = Qv.mean(0) + S.V[top].mean(0)
    q2 /= np.linalg.norm(q2)
    extra = np.setdiff1d(B.topk(q2, elig), cand)
    if len(extra):
        s1 = np.concatenate([s1, S.V.rows_dot(extra, Qv.T).max(axis=1)])
        cand = np.concatenate([cand, extra])
    s = np.maximum(s1, S.V.rows_dot(cand, q2))
    o = np.argsort(-s, kind="stable")
    dense = [S.vcodes[cand[n]] for n in o[:1000]]
    return [dense, S.bm.rank(bq, keep=keep) if bq.strip() else []], Qv, cand


def float_dense_top(S, Vf, Qv, keep, k=100):
    """Diagnostics only: the float dense list's top k (own_lists' dense with float32 item vectors)."""
    s = (Vf @ Qv.T).max(axis=1)
    sg = np.where(S.gate, s, -9.0)
    if keep is not None:
        sg = np.where(np.array([keep(c) for c in S.vcodes]), sg, -9.0)
    top = np.argsort(-sg)[:5]
    q2 = Qv.mean(0) + Vf[top].mean(0)
    q2 /= np.linalg.norm(q2)
    s = np.maximum(s, Vf @ q2)
    return S._dense_rank(s, keep)[:k]
