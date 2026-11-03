"""PROTOTYPE ONLY - shared helpers for the Q3 speed experiments (round 2): load B3 once, time searches, percentiles.

B3 = stack.py's Stack with --opt hyde=1 on the te-v1c enrichment index. stack.py is imported, never edited.
The instant path = the same Stack called with an empty rewrite (phrases [], keywords [], no hypothetical captions),
so the raw query is the only phrase and there is no HyDE vector. More-like-this searches never use the rewrite.

Reads method-side data only (corpus, enrichment, queries.jsonl). Never opens labels or scores.
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
from corpus import DATA, Corpus, code_of, load_queries  # noqa: E402
from e9_enrich_search import EnrichIndex  # noqa: E402
import stack  # noqa: E402

EMPTY = {"phrases": [], "keywords": [], "hypothetical_captions": []}
RUNS = os.path.join(DATA, "runs")
REWRITES = os.path.join(RUNS, "rewrites")


def load_b3():
    """Returns (Stack with hyde=1, Corpus). Takes ~20-30 s (BM25 indexes are built lazily on first search)."""
    t = time.time()
    C = Corpus("bge_full")
    by_code = {code_of(it): it for it in C.items.values()}
    E = EnrichIndex(stack.ENRICH, by_code)
    S = stack.Stack(C, E, stack.parse_opts(["hyde=1"]))
    print(f"loaded B3 in {time.time() - t:.1f} s", file=sys.stderr)
    return S, C


def warm(S, qs, parse_of=lambda q: EMPTY):
    """One untimed pass so lazy indexes, the ONNX session and caches are built before timing."""
    for q in qs:
        S.run(q, None if q["examples"] else parse_of(q))


def timed_search(S, q, parse):
    t = time.perf_counter()
    fused = S.run(q, None if q["examples"] else parse)
    return fused, time.perf_counter() - t


def pct(xs, p):
    return round(float(np.percentile(np.asarray(xs, dtype=float), p)), 3) if len(xs) else None


def summary(xs):
    return {"n": len(xs), "p50_s": pct(xs, 50), "p95_s": pct(xs, 95), "mean_s": round(float(np.mean(xs)), 3) if xs
            else None, "max_s": round(float(np.max(xs)), 3) if xs else None}


def load_run(path):
    return json.load(open(path))["queries"]


def write_run(path, method, emb, meta, queries):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    json.dump({"method": method, "embedding": emb, "meta": meta, "queries": queries}, open(path, "w"))
    print(f"wrote {path}: {len(queries)} queries")


def dev_queries():
    return load_queries("dev")


def rewrite_secs(path, typed_ids):
    """Per-call rewrite seconds recorded in a rewrite file's _meta (typed searches only)."""
    pq = json.load(open(path))["_meta"]["per_query"]
    return [pq[i]["seconds"] for i in typed_ids if i in pq]
