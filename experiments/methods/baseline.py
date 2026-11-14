"""PROTOTYPE ONLY - current best search (30 Oct 2026), as a reproducible run file.

Typed searches: AI query rewrite (phrases + keywords) -> dense (max over phrases, info-ok items only,
+ Rocchio pseudo-relevance feedback from top 5) + BM25 over the 'full' text view -> RRF (k=60).
More-like-this: centroid of the examples (dense) + BM25 on the examples' text -> RRF.

Rewrites come from data/evals/query_parses.json by default (hand-simulated). --parses PATH swaps in another
parses file of the same shape (e.g. a real LLM rewrite from methods/llm_rewrite.py; its `_meta` cost and
latency are copied into the run's meta for the queries run). --norewrite uses the raw query only
(phrases = [], keywords = []). Filters always come from queries.jsonl.

usage: python experiments/methods/baseline.py --emb bge_full --variant hybrid_prf --out runs/x.json [--split dev]
       [--parses PATH | --norewrite]
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
ap.add_argument("--parses", default=os.path.join(DATA, "evals", "query_parses.json"))
ap.add_argument("--norewrite", action="store_true", help="raw query only: no phrases, no keywords")
a = ap.parse_args()

t0 = time.time()
C = Corpus(a.emb)
if a.qcache:
    C.qcache = json.load(open(a.qcache))
P = {} if a.norewrite else json.load(open(a.parses))
RW = P.get("_meta", {})
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
        p = {"phrases": [], "keywords": []} if a.norewrite else P[q["id"]]
        phrases = [q["query"]] + p["phrases"]
        d = rank(dense(phrases, m & ok, a.variant == "hybrid_prf"), m & ok)
        b = rank(C.bm25(" ".join([q["query"]] + p["keywords"]), "full"), m)
        out[q["id"]] = {"dense": d, "bm25": b}.get(a.variant, rrf(d, b))
    lat.append(time.time() - t)
meta = {"wall_s": round(time.time() - t0, 1), "query_p50_s": round(float(np.median(lat)), 3), "cost_usd": 0,
        "rewrite": "none" if a.norewrite else os.path.basename(a.parses)}
if RW:  # real rewrite: cost and latency of the rewrite calls for the queries in this run
    pq = [RW["per_query"][k] for k in out if k in RW.get("per_query", {})]
    meta.update({"cost_usd": round(sum(v["cost_usd"] for v in pq), 6), "rewrite_n": len(pq),
                 "rewrite_p50_s": round(float(np.median([v["seconds"] for v in pq])), 3) if pq else None,
                 "prompt_version": RW.get("prompt_version"), "model": RW.get("model"),
                 "reasoning_effort": RW.get("reasoning_effort")})
    meta["query_plus_rewrite_p50_s"] = round(meta["query_p50_s"] + (meta["rewrite_p50_s"] or 0), 3)
tag = "+norewrite" if a.norewrite else (f"+{RW.get('prompt_version')}_{RW.get('model')}" if RW else "")
write_run(a.out, f"baseline:{a.variant}{tag}", C, out, meta)
print("wrote", a.out)
