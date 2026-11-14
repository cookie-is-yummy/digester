"""PROTOTYPE ONLY - method-side corpus access for search experiments.

Reads only method-side data (corpus + queries). It never opens data/evals/labels/.

Data root: $DIGESTER_DATA (default: <repo>/data). Layout in experiments/README.md.
"""
import json
import os
import sys

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.preprocessing import normalize

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DATA = os.environ.get("DIGESTER_DATA", os.path.join(REPO, "data"))
sys.path.insert(0, HERE)
from common import info_class  # noqa: E402


def fix_ws(s):
    return " ".join((s or "").split())


def code_of(item):
    return item["dedup_key"].split(":", 1)[1]


class Corpus:
    """All items from the export. `emb` names a folder under data/corpus/emb/ holding ids.json + emb.npy.

    Rows = items that have a vector. Items without a vector (no caption) can still be ranked by
    methods that give them text (e.g. enrichment) via `extra_text`.
    """

    def __init__(self, emb="bge_full", extra_text=None):
        self.items = {}
        for line in open(os.path.join(DATA, "corpus", "items.jsonl"), encoding="utf-8"):
            it = json.loads(line)
            self.items[it["id"]] = it
        d = os.path.join(DATA, "corpus", "emb", emb)
        self.ids = json.load(open(os.path.join(d, "ids.json")))
        self.V = normalize(np.load(os.path.join(d, "emb.npy")).astype(np.float32))
        self.emb_name = emb
        self.code = [code_of(self.items[k]) for k in self.ids]
        self.by_code = {c: n for n, c in enumerate(self.code)}
        self.first = np.array([self.items[k].get("first_seen_at") or "9999" for k in self.ids])
        self.kinds = [set(self.items[k]["interaction_kinds"]) for k in self.ids]
        self.info = np.array([info_class(self.items[k]) for k in self.ids])
        self.extra_text = extra_text or {}  # {code: text} e.g. enrichment output appended to the search text
        self._bm25 = {}
        self._model = None
        self.qcache = None  # {phrase: vector} for API-embedded queries

    # ---------- text views ----------
    def text(self, n, view="full"):
        it = self.items[self.ids[n]]
        pd = it["platform_data"]
        cap = it.get("caption") or ""
        tags = pd.get("hashtags") or []
        parts = [cap[:600], " ".join("#" + t for t in tags[:15])]
        if view in ("cap_tags_creator", "full"):
            parts.append(f"by @{pd.get('owner_handle') or ''} {pd.get('owner_name') or ''}")
        if view == "full":
            import wordninja
            parts.append(" ".join(" ".join(wordninja.split(t)) for t in tags[:15]))
            parts.append(" ".join(wordninja.split(pd.get("owner_handle") or "")))
        extra = self.extra_text.get(self.code[n])
        if extra:
            parts.append(extra)
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
        self._bm25[view] = (cv, sparse.csr_matrix((w, (tf.row, tf.col)), shape=tf.shape))
        return self._bm25[view]

    def bm25(self, query, view="full"):
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

    def qvecs(self, phrases):
        if self.qcache is not None:
            return normalize(np.array([self.qcache[p] for p in phrases], dtype=np.float32))
        return normalize(np.array(list(self.model().query_embed(phrases)), dtype=np.float32))

    # ---------- filters ----------
    def mask(self, filters):
        m = np.ones(len(self.ids), bool)
        if filters.get("before"):
            m &= self.first < filters["before"]
        if filters.get("kinds"):
            want = set(filters["kinds"])
            m &= np.array([bool(k & want) for k in self.kinds])
        return m


def load_queries(split=None):
    """Method-side queries (no answers). split: None | 'dev' | 'test'."""
    qs = [json.loads(l) for l in open(os.path.join(DATA, "evals", "queries.jsonl"))]
    if split:
        keep = set(json.load(open(os.path.join(DATA, "evals", "split.json")))[split])
        qs = [q for q in qs if q["id"] in keep]
    return qs


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


def write_run(path, method, corpus, ranked_rows, meta=None, depth=1000):
    """ranked_rows: {query_id: [row, ...]}. Stored as content codes so any corpus/embedding can be scored."""
    run = {"method": method, "embedding": corpus.emb_name, "meta": meta or {},
           "queries": {q: [corpus.code[n] for n in rows[:depth]] for q, rows in ranked_rows.items()}}
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    json.dump(run, open(path, "w"))
    return path
