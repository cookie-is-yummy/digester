"""PROTOTYPE ONLY - round 3 (YouTube) shared helpers: items, interactions, text views, vector stores, BM25.

Method side only: reads $DIGESTER_DATA/corpus, evals/queries.jsonl, evals/split.json and (reference arm only)
ref/api_tier0.jsonl. Never opens evals/labels/.

Text views (one variable each):
  allowed : Takeout title + "by <channel>" + the user's named playlist names ("Watch later" left out: it is an
            interaction, used by the intent step, not content). Items with no Takeout title get no vector, but
            their channel/playlist text (if any) is still in the BM25 index.
  api     : RESEARCH-ONLY reference. API title + "by <channel>" + tags (hashtag form and plain) + chapter titles
            + description without URLs/chapter lines [:600] + the same playlist names. Never mixed into
            allowed runs.
Vector stores live in $DIGESTER_DATA/corpus/emb/<name>/ (ids.json + emb.npy float16). Corpus views use item ids
(same convention as lib/corpus.py); enrichment and query stores use content codes / the query strings.
"""
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.preprocessing import normalize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
from corpus import DATA, fix_ws

EMB = os.path.join(DATA, "corpus", "emb")
EMB_MODEL, EMB_DIM = "text-embedding-3-small", 512
WATCH_LATER = "Watch later"
_URL = re.compile(r"https?://\S+")


def code_of(it):
    return it["dedup_key"].split(":", 1)[1]


class YT:
    """All items (115k) in file order, with per-item interaction summaries."""

    def __init__(self):
        self.items = [json.loads(l) for l in open(os.path.join(DATA, "corpus", "items.jsonl"), encoding="utf-8")]
        self.codes = [code_of(it) for it in self.items]
        self.pos = {c: n for n, c in enumerate(self.codes)}
        self.id_pos = {it["id"]: n for n, it in enumerate(self.items)}
        N = len(self.items)
        self.inter = [[] for _ in range(N)]  # (kind, at, collection_name)
        for l in open(os.path.join(DATA, "corpus", "interactions.jsonl")):
            r = json.loads(l)
            n = self.id_pos.get(r["item_id"])
            if n is not None:
                self.inter[n].append((r["kind"], r["at"] or "", r.get("collection_name")))
        pd = [it["platform_data"] for it in self.items]
        self.title = [(it.get("caption") or "").strip() for it in self.items]
        self.channel = [(p.get("owner_name") or "").strip() for p in pd]
        self.watch_count = np.array([p.get("watch_count") or 0 for p in pd])
        self.duration = np.array([p.get("duration_s") if p.get("duration_s") is not None else -1 for p in pd])
        self.available = np.array([bool(p.get("available")) for p in pd])
        self.liked = np.array(["like" in it["interaction_kinds"] for it in self.items])
        self.saved = np.array(["playlist" in it["interaction_kinds"] for it in self.items])
        self.watched = self.watch_count > 0
        self.depth = [it["processing_depth"] for it in self.items]
        self.first = np.array([it.get("first_seen_at") or "9999" for it in self.items])
        self.last = np.array([max([a for _, a, _ in xs] or [""]) for xs in self.inter])
        self.playlists = [sorted({p for p in (q.get("collections") or []) if p != WATCH_LATER}) for q in pd]
        low = [t.lower() for t in self.title]
        d = self.duration
        self.short = (d >= 0) & ((d <= 60) | ((d <= 180) & np.array(["#short" in t for t in low])))

    def gated(self):
        """Tier-1 gate (BRIEF-3): processing depth light/full or watched 3+ times."""
        return np.array([dp in ("light", "full") or wc >= 3 for dp, wc in zip(self.depth, self.watch_count)])

    # ---------- text views ----------
    def allowed_text(self, n):
        parts = [self.title[n]]
        if self.channel[n]:
            parts.append(f"by {self.channel[n]}")
        if self.playlists[n]:
            parts.append("playlists: " + ", ".join(self.playlists[n]))
        return fix_ws(" ".join(p for p in parts if p))

    def api_text(self, n, row):
        if not row or not row.get("ok"):
            return self.allowed_text(n)
        ch = (row.get("creator") or {}).get("name") or self.channel[n]
        tags = row.get("hashtags") or []
        parts = [row.get("title") or self.title[n], f"by {ch}" if ch else "",
                 " ".join("#" + t.replace(" ", "") for t in tags[:15]), " ".join(tags[:15])]
        if row.get("chapters"):
            parts.append("chapters: " + " · ".join(c["title"] for c in row["chapters"]))
        parts.append(clean_description(row.get("caption"), row.get("chapters"))[:600])
        if self.playlists[n]:
            parts.append("playlists: " + ", ".join(self.playlists[n]))
        return fix_ws(" ".join(p for p in parts if p))


def clean_description(desc, chapters):
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "youtube"))
    from api_enrich import (
        clean_description as cd,  # same cleaning as the tier-0 enricher
    )
    return cd(desc or "", chapters or [])


def load_api_rows():
    """RESEARCH-ONLY reference arm."""
    return {r["code"]: r for r in (json.loads(l) for l in open(os.path.join(DATA, "ref", "api_tier0.jsonl")))}


def load_queries():
    return [json.loads(l) for l in open(os.path.join(DATA, "evals", "queries.jsonl"))]


def outside_examples():
    """{code: text in the allowed-view format} for more-like-this examples outside the library (from the given
    'Channel - Title' string)."""
    out = {}
    for q in load_queries():
        for e in q.get("examples_outside_library") or []:
            t = e.get("title") or ""
            ch, _, ti = t.partition(" - ")
            out[e["video_id"]] = fix_ws(f"{ti} by {ch}") if ti else fix_ws(t)
    return out


# ---------- vectors ----------
def embed_texts(texts, purpose, batch=1000, workers=4):
    import ai
    chunks = [texts[i:i + batch] for i in range(0, len(texts), batch)]
    t0 = time.time()

    def one(ch):
        for att in range(10):
            try:
                return ai.openai_embed([t[:6000] or " " for t in ch], model=EMB_MODEL, dimensions=EMB_DIM,
                                       purpose=purpose)
            except Exception as e:
                if "budget stop" in str(e) or att == 9:
                    raise
                time.sleep(min(60, 4 * 2 ** att) if "429" in str(e) else 3 * (att + 1))

    with ThreadPoolExecutor(workers) as ex:
        out = [v for vs in ex.map(one, chunks) for v in vs]
    el = time.time() - t0
    print(f"  embedded {len(texts)} texts in {el:.1f}s ({len(texts) / max(el, 1e-9):.0f}/s), {purpose}", flush=True)
    return np.array(out, dtype=np.float32)


def save_store(name, ids, V):
    d = os.path.join(EMB, name)
    os.makedirs(d, exist_ok=True)
    json.dump(ids, open(os.path.join(d, "ids.json"), "w"))
    np.save(os.path.join(d, "emb.npy"), V.astype(np.float16))


def load_store(name):
    d = os.path.join(EMB, name)
    if not os.path.exists(os.path.join(d, "ids.json")):
        return [], np.zeros((0, EMB_DIM), np.float32)
    return json.load(open(os.path.join(d, "ids.json"))), normalize(np.load(os.path.join(d, "emb.npy")).astype(np.float32))


class QueryVecs:
    """Cached query/HyDE vectors (oai512_queries store). get() embeds and saves any missing strings."""

    def __init__(self, name="oai512_queries"):
        self.name = name
        ids, V = load_store(name)
        self.vec = {s: V[k] for k, s in enumerate(ids)}

    def get(self, texts):
        miss = sorted({t for t in texts if t not in self.vec})
        if miss:
            V = normalize(embed_texts(miss, "yt_query_vectors", batch=500, workers=1))
            for s, v in zip(miss, V):
                self.vec[s] = v
            ids = list(self.vec)
            save_store(self.name, ids, np.array([self.vec[s] for s in ids]))
        return np.array([self.vec[t] for t in texts], dtype=np.float32)


# ---------- BM25 ----------
class BM25:
    """Same tokenisation and k1/b as lib/corpus.py (uni+bigrams, k1 1.2, b 0.75) over {key: text}."""

    def __init__(self, texts):
        self.keys = list(texts)
        self.pos = {k: n for n, k in enumerate(self.keys)}
        cv = CountVectorizer(token_pattern=r"(?u)\b\w\w+\b", ngram_range=(1, 2), min_df=1)
        tf = cv.fit_transform([texts[k].lower() for k in self.keys]).tocsc().astype(np.float32)
        N = tf.shape[0]
        df = np.diff(tf.indptr)
        idf = np.log(1 + (N - df + 0.5) / (df + 0.5)).astype(np.float32)
        dl = np.asarray(tf.sum(axis=1)).ravel()
        k1, b = 1.2, 0.75
        tf = tf.tocoo()
        w = tf.data * (k1 + 1) / (tf.data + k1 * (1 - b + b * dl[tf.row] / max(dl.mean(), 1e-9))) * idf[tf.col]
        self.cv, self.W = cv, sparse.csr_matrix((w, (tf.row, tf.col)), shape=tf.shape)

    def scores(self, query):
        q = self.cv.transform([query.lower()])
        q.data[:] = 1
        return np.asarray((self.W @ q.T).todense()).ravel()

    def rank(self, query, exclude=(), keep=None, depth=1000):
        s = self.scores(query)
        s[s <= 0] = -np.inf
        for k in exclude:
            if k in self.pos:
                s[self.pos[k]] = -np.inf
        order = np.argsort(-s)
        out = []
        for n in order:
            if not np.isfinite(s[n]):
                break
            k = self.keys[n]
            if keep is None or keep(k):
                out.append(k)
                if len(out) >= depth:
                    break
        return out
