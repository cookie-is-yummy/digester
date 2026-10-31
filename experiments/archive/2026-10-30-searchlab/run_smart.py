"""PROTOTYPE ONLY - cheap 'work smart' ideas on top of the best setup (rewrite + dense + keywords, RRF).

A. baseline           : dense over info-ok items only (thin items excluded)
B. creator backfill   : thin items get their creator's centroid vector (if creator has >=2 info-ok items) and rejoin dense search
C. pseudo-relevance   : query vector += mean of top-5 dense hits (Rocchio), search again
D. B + C
MLT: E. dense+bm25 (baseline) ; F. + same-creator expansion as a third ranked list

usage: venv/bin/python -I searchlab/run_smart.py <ids.json> <emb.npy> [qcache.json] --eval <evalset>
"""
import collections
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lab import Corpus, load_eval, metrics, rank, rrf  # noqa: E402

a = sys.argv[1:]
C = Corpus(a[0], a[1])
if len(a) > 2 and not a[2].startswith("--"):
    C.qcache = json.load(open(a[2]))
Q = load_eval(C, a[a.index("--eval") + 1])
P = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "query_parses.json")))
ok = C.info == "ok"

# creator centroids from info-ok items
handle = np.array([C.items[k]["platform_data"].get("owner_handle") or "" for k in C.ids])
by_h = collections.defaultdict(list)
for n, h in enumerate(handle):
    if h and ok[n]:
        by_h[h].append(n)
VB = C.V.copy()
backfill = np.zeros(len(C.ids), bool)
for n in np.where(~ok)[0]:
    rows = by_h.get(handle[n], [])
    if len(rows) >= 2:
        c = C.V[rows].mean(0)
        VB[n] = c / np.linalg.norm(c)
        backfill[n] = True
print(f"thin items {int((~ok).sum())}, backfilled from creator {int(backfill.sum())}")


def dense_scores(V, phrases, prf=False):
    Qv = C.qvecs(phrases)
    s = (V @ Qv.T).max(axis=1)
    if prf:
        top = np.argsort(-np.where(ok, s, -9))[:5]
        q2 = Qv.mean(0) + V[top].mean(0)
        q2 /= np.linalg.norm(q2)
        s = np.maximum(s, V @ q2)
    return s


out = collections.defaultdict(list)
for q in Q:
    m, rel = q["mask"], q["rel_rows"]
    if q["examples"]:
        ex = q["example_rows"]
        cen = C.V[ex].mean(0)
        cen /= np.linalg.norm(cen)
        d = rank(C.V @ cen, m & ok, ex)
        b = rank(C.bm25(" ".join(C.text(n, "full") for n in ex), "full"), m, ex)
        same = [n for h in {handle[e] for e in ex} for n in by_h.get(h, []) if n not in ex and m[n]]
        same = sorted(same, key=lambda n: -float(C.V[n] @ cen))
        out["mlt_base"].append(metrics(rrf(d, b), rel))
        out["mlt_creator"].append(metrics(rrf(d, b, same), rel))
        continue
    p = P[q["id"]]
    phrases = [q["query"]] + p["phrases"]
    bm = rank(C.bm25(" ".join([q["query"]] + p["keywords"]), "full"), m)
    runs = {
        "A_base": rank(dense_scores(C.V, phrases), m & ok),
        "B_backfill": rank(dense_scores(VB, phrases), m & (ok | backfill)),
        "C_prf": rank(dense_scores(C.V, phrases, prf=True), m & ok),
        "D_backfill_prf": rank(dense_scores(VB, phrases, prf=True), m & (ok | backfill)),
    }
    for k, r in runs.items():
        out[k + "_dense"].append(metrics(r, rel))
        out[k + "_hybrid"].append(metrics(rrf(r, bm), rel))
for k, v in out.items():
    print(f"{k:24s} nDCG@10 {np.mean([x['ndcg10'] for x in v]):.3f}  P@10 {np.mean([x['p10'] for x in v]):.3f}  "
          f"R@100 {np.mean([x['r100'] for x in v]):.3f}  MRR {np.mean([x['mrr'] for x in v]):.3f}")
