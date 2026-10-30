"""PROTOTYPE ONLY - current best search (30 Oct 2026), as a reproducible run file.

Typed searches: AI query rewrite (phrases + keywords) -> dense (max over phrases, info-ok items only,
+ Rocchio pseudo-relevance feedback from top 5) + BM25 over the 'full' text view -> RRF (k=60).
More-like-this: centroid of the examples (dense) + BM25 on the examples' text -> RRF.

Rewrites come from data/evals/query_parses.json (hand-simulated; replacing them with a real LLM call
is an open experiment).

usage: python experiments/methods/baseline.py --emb bge_full --variant hybrid_prf --out runs/x.json [--split dev]
variants: dense | bm25 | hybrid | hybrid_prf
"""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from corpus import DATA, Corpus, load_queries, rank, rrf, write_run  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--emb", default="bge_full")
ap.add_argument("--variant", default="hybrid_prf")
ap.add_argument("--split", default=None)
ap.add_argument("--qcache", default=None, help="json {phrase: vector} for API-embedded queries")
ap.add_argument("--out", required=True)
a = ap.parse_args()

t0 = time.time()
C = Corpus(a.emb)
if a.qcache:
    C.qcache = json.load(open(a.qcache))
P = json.load(open(os.path.join(DATA, "evals", "query_parses.json")))
ok = C.info == "ok"


def dense(phrases, m, prf):
    Qv = C.qvecs(phrases)
    s = (C.V @ Qv.T).max(axis=1)
    if prf:
        top = np.argsort(-np.where(m, s, -9))[:5]
        q2 = Qv.mean(0) + C.V[top].mean(0)
        q2 /= np.linalg.norm(q2)
        s = np.maximum(s, C.V @ q2)
    return s


out, lat = {}, []
for q in load_queries(a.split):
    t = time.time()
    m = C.mask(q["filters"])
    if q["examples"]:
        ex = [C.by_code[c] for c in q["examples"] if c in C.by_code]
        cen = C.V[ex].mean(0)
        cen /= np.linalg.norm(cen)
        d = rank(C.V @ cen, m & ok, ex)
        b = rank(C.bm25(" ".join(C.text(n, "full") for n in ex), "full"), m, ex)
        out[q["id"]] = {"dense": d, "bm25": b}.get(a.variant, rrf(d, b))
    else:
        p = P[q["id"]]
        phrases = [q["query"]] + p["phrases"]
        d = rank(dense(phrases, m & ok, a.variant == "hybrid_prf"), m & ok)
        b = rank(C.bm25(" ".join([q["query"]] + p["keywords"]), "full"), m)
        out[q["id"]] = {"dense": d, "bm25": b}.get(a.variant, rrf(d, b))
    lat.append(time.time() - t)
write_run(a.out, f"baseline:{a.variant}", C, out,
          {"wall_s": round(time.time() - t0, 1), "query_p50_s": round(float(np.median(lat)), 3), "cost_usd": 0})
print("wrote", a.out)
