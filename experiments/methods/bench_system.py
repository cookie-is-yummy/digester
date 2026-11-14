"""PROTOTYPE ONLY - phase 2 system benchmark of the baseline search (no labels).

Measures, on this machine: corpus load, bge-small indexing speed (items/s on N threads), BM25 index
build time, per-query latency of the baseline (dense+PRF, BM25, RRF; rewrite excluded), storage per item,
and a synthetic 100k-item scale test (random vectors + replicated BM25 matrix) for query latency.

usage: python experiments/methods/bench_system.py [--n-embed 1000] [--threads 4] --json OUT.json
"""
import argparse
import json
import os
import sys
import time

import numpy as np
from scipy import sparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from corpus import DATA, Corpus, load_queries, rank, rrf  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--n-embed", type=int, default=1000)
ap.add_argument("--threads", type=int, default=os.cpu_count())
ap.add_argument("--json", required=True)
a = ap.parse_args()
R = {"cpu_count": os.cpu_count(), "threads": a.threads}

t = time.time()
C = Corpus("bge_full")
R["corpus_load_s"] = round(time.time() - t, 2)
R["n_items"] = len(C.items)
R["n_vectors"] = len(C.ids)

# indexing speed: embed n items of the 'full' view
from fastembed import TextEmbedding  # noqa: E402
m = TextEmbedding(model_name="BAAI/bge-small-en-v1.5", threads=a.threads)
list(m.embed(["warm up"]))
texts = [C.text(n, "full") for n in range(a.n_embed)]
t = time.time()
list(m.embed(texts, batch_size=64))
dt = time.time() - t
R["embed_items_per_s"] = round(a.n_embed / dt, 1)
R["embed_s_per_1000"] = round(1000 * dt / a.n_embed, 1)
R["avg_text_chars"] = round(float(np.mean([len(x) for x in texts])), 0)

t = time.time()
cv, W = C.bm25_index("full")
R["bm25_build_s"] = round(time.time() - t, 2)
R["bm25_vocab"] = len(cv.vocabulary_)
R["bm25_nnz_per_item"] = round(W.nnz / W.shape[0], 1)

# storage per item
emb_bytes = os.path.getsize(os.path.join(DATA, "corpus", "emb", "bge_full", "emb.npy"))
R["storage_bytes_per_item"] = {
    "vector_bge384_fp16": round(emb_bytes / len(C.ids)),
    "search_text_utf8": round(float(np.mean([len(C.text(n, "full").encode()) for n in range(len(C.ids))]))),
    "bm25_postings_est(4B id + 4B weight)": round(W.nnz * 8 / W.shape[0]),
}

# query latency of the baseline method (no LLM rewrite; rewrite from query_parses)
P = json.load(open(os.path.join(DATA, "evals", "query_parses.json")))
ok = C.info == "ok"
lat = []
for rep in range(3):
    for q in load_queries():
        if q["examples"]:
            continue
        t = time.time()
        msk = C.mask(q["filters"])
        p = P[q["id"]]
        Qv = C.qvecs([q["query"]] + p["phrases"])
        s = (C.V @ Qv.T).max(axis=1)
        top = np.argsort(-np.where(msk & ok, s, -9))[:5]
        q2 = Qv.mean(0) + C.V[top].mean(0)
        s = np.maximum(s, C.V @ (q2 / np.linalg.norm(q2)))
        d = rank(s, msk & ok)
        b = rank(C.bm25(" ".join([q["query"]] + p["keywords"]), "full"), msk)
        rrf(d, b)
        lat.append(time.time() - t)
R["query_latency_s"] = {"p50": round(float(np.median(lat)), 3), "p95": round(float(np.percentile(lat, 95)), 3),
                        "n": len(lat), "note": "excludes LLM rewrite; includes query embedding of 1-4 phrases"}

# synthetic 100k-item scale test (dense dot + argsort, BM25 sparse matvec)
N = 100_000
Vb = np.random.default_rng(0).standard_normal((N, 384)).astype(np.float32)
Vb /= np.linalg.norm(Vb, axis=1, keepdims=True)
Wb = sparse.vstack([W] * (N // W.shape[0] + 1))[:N].tocsr()
qv = Vb[:3]
lat_d, lat_b = [], []
for _ in range(10):
    t = time.time()
    s = (Vb @ qv.T).max(axis=1)
    np.argsort(-s)
    lat_d.append(time.time() - t)
    qq = cv.transform(["street photography tips"])
    qq.data[:] = 1
    t = time.time()
    sb = np.asarray((Wb @ qq.T).todense()).ravel()
    np.argsort(-sb)
    lat_b.append(time.time() - t)
R["scale_100k"] = {"dense_exact_p50_s": round(float(np.median(lat_d)), 3), "bm25_p50_s": round(float(np.median(lat_b)), 3),
                   "dense_fp32_ram_mb": round(Vb.nbytes / 1e6), "note": "synthetic vectors; full argsort (top-k via argpartition is faster)"}
json.dump(R, open(a.json, "w"), indent=1)
print(json.dumps(R, indent=1))
