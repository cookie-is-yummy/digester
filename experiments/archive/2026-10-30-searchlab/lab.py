"""PROTOTYPE ONLY - search lab: retrieval methods + metrics over the graded eval set.

Corpus = every item with a caption (embedded). Methods are composable: dense, bm25, rrf, rerank, more-like-this.
"""
import json
import math
import sys
import os
import re
import time

import numpy as np
import wordninja
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.preprocessing import normalize

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT2 = os.path.join(ROOT, "prototype", "out_v2")


def fix_ws(s):
    return " ".join((s or "").split())


class Corpus:
    def __init__(self, emb_ids=f"{OUT2}/embeddings/all_ids.json", emb=f"{OUT2}/embeddings/all_bge.npy"):
        self.items = {}
        for l in open(f"{OUT2}/items.jsonl", encoding="utf-8"):
            it = json.loads(l)
            self.items[it["id"]] = it
        self.ids = json.load(open(emb_ids))
        self.V = np.load(emb).astype(np.float32)
        self.row = {k: n for n, k in enumerate(self.ids)}
        self.code = [self.items[k]["dedup_key"].split(":", 1)[1] for k in self.ids]
        self.by_code = {c: n for n, c in enumerate(self.code)}
        self.first = np.array([self.items[k].get("first_seen_at") or "9999" for k in self.ids])
        self.kinds = [set(self.items[k]["interaction_kinds"]) for k in self.ids]
        self._bm25 = {}
        self._model = None
        sys.path.insert(0, os.path.join(ROOT, "prototype"))
        from common import info_class
        self.info = np.array([info_class(self.items[k]) for k in self.ids])

    # ---------- text views ----------
    def text(self, n, view="cap_tags"):
        it = self.items[self.ids[n]]
        pd = it["platform_data"]
        cap = it.get("caption") or ""
        tags = pd.get("hashtags") or []
        parts = [cap[:600], " ".join("#" + t for t in tags[:15])]
        if view in ("cap_tags_creator", "full"):
            h = pd.get("owner_handle") or ""
            parts.append(f"by @{h} {pd.get('owner_name') or ''}")
        if view == "full":  # hashtags split into words: #geometrynodes -> geometry nodes
            parts.append(" ".join(" ".join(wordninja.split(t)) for t in tags[:15]))
            h = pd.get("owner_handle") or ""
            parts.append(" ".join(wordninja.split(h)))
        return fix_ws(" ".join(parts))

    # ---------- BM25 ----------
    def bm25_index(self, view):
        if view in self._bm25:
            return self._bm25[view]
        docs = [self.text(n, view).lower() for n in range(len(self.ids))]
        cv = CountVectorizer(token_pattern=r"(?u)\b\w\w+\b", ngram_range=(1, 2), min_df=1)
        tf = cv.fit_transform(docs).tocsc().astype(np.float32)
        N = tf.shape[0]
        df = np.diff(tf.indptr)
        idf = np.log(1 + (N - df + 0.5) / (df + 0.5)).astype(np.float32)
        dl = np.asarray(tf.sum(axis=1)).ravel()
        k1, b = 1.2, 0.75
        tf = tf.tocoo()
        denom = tf.data + k1 * (1 - b + b * dl[tf.row] / dl.mean())
        w = tf.data * (k1 + 1) / denom * idf[tf.col]
        W = sparse.csr_matrix((w, (tf.row, tf.col)), shape=tf.shape)
        self._bm25[view] = (cv, W)
        return cv, W

    def bm25(self, query, view="cap_tags"):
        cv, W = self.bm25_index(view)
        q = cv.transform([query.lower()])
        q.data[:] = 1
        return np.asarray((W @ q.T).todense()).ravel()

    # ---------- dense ----------
    def model(self):
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5", threads=os.cpu_count())
        return self._model

    qcache = None

    def qvecs(self, phrases):
        if self.qcache is not None:
            return normalize(np.array([self.qcache[p] for p in phrases], dtype=np.float32))
        return normalize(np.array(list(self.model().query_embed(phrases))))

    def dense(self, phrases, V=None):
        V = self.V if V is None else V
        Q = self.qvecs(phrases)
        return (V @ Q.T).max(axis=1)

    # ---------- filters ----------
    def mask(self, filters):
        m = np.ones(len(self.ids), bool)
        if filters.get("before"):
            m &= self.first < filters["before"]
        if filters.get("kinds"):
            want = set(filters["kinds"])
            m &= np.array([bool(k & want) for k in self.kinds])
        return m


def rank(scores, mask=None, exclude=()):
    s = scores.astype(np.float64).copy()
    if mask is not None:
        s[~mask] = -np.inf
    for n in exclude:
        s[n] = -np.inf
    order = np.argsort(-s)
    return [int(n) for n in order if np.isfinite(s[n])]


def rrf(*rankings, k=60, depth=1000):
    sc = {}
    for r in rankings:
        for i, n in enumerate(r[:depth]):
            sc[n] = sc.get(n, 0.0) + 1.0 / (k + i + 1)
    return [n for n, _ in sorted(sc.items(), key=lambda x: -x[1])]


def metrics(ranked, rel, k=10):
    """rel: {row: grade}. graded nDCG@k, recall@20/@100 (grade>=1), recall2@100 (grade 2), MRR, P@10."""
    if not rel:
        return None
    gains = [rel.get(n, 0) for n in ranked[:k]]
    dcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sorted(rel.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    pos = {n: i for i, n in enumerate(ranked[:1000])}
    first = min((pos[n] for n in rel if n in pos), default=None)
    conf = [n for n, g in rel.items() if g == 2]
    return {
        "ndcg10": dcg / idcg if idcg else 0.0,
        "p10": sum(1 for n in ranked[:10] if n in rel) / 10,
        "r20": sum(1 for n in rel if pos.get(n, 9e9) < 20) / len(rel),
        "r100": sum(1 for n in rel if pos.get(n, 9e9) < 100) / len(rel),
        "r100_conf": (sum(1 for n in conf if pos.get(n, 9e9) < 100) / len(conf)) if conf else None,
        "mrr": 1.0 / (first + 1) if first is not None else 0.0,
    }


def load_eval(corpus, path=os.path.join(HERE, "evalset.jsonl")):
    qs = []
    for l in open(path):
        q = json.loads(l)
        m = corpus.mask(q["filters"])
        rel = {corpus.by_code[c]: g for c, g in q["relevant"].items() if c in corpus.by_code and m[corpus.by_code[c]]}
        q["rel_rows"] = rel
        q["neg_rows"] = [corpus.by_code[c] for c in q["hard_negatives"] if c in corpus.by_code]
        q["example_rows"] = [corpus.by_code[c] for c in q["examples"] if c in corpus.by_code]
        q["mask"] = m
        qs.append(q)
    return qs


class Timer:
    def __enter__(self):
        self.t = time.time()
        return self

    def __exit__(self, *a):
        self.s = time.time() - self.t
