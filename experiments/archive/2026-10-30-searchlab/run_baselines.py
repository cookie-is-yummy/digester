"""PROTOTYPE ONLY - baseline search methods on the eval set.

usage: venv/bin/python -I searchlab/run_baselines.py [--rerank MODEL] [--emb ids.json emb.npy] [--tag NAME]
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lab import Corpus, Timer, load_eval, metrics, rank, rrf  # noqa: E402

args = sys.argv[1:]
RERANK = args[args.index("--rerank") + 1] if "--rerank" in args else None
TAG = args[args.index("--tag") + 1] if "--tag" in args else "base"
GATE = "--gate" in args
if "--emb" in args:
    i = args.index("--emb")
    C = Corpus(args[i + 1], args[i + 2])
else:
    C = Corpus()
if "--qcache" in args:
    C.qcache = json.load(open(args[args.index("--qcache") + 1]))
Q = load_eval(C, args[args.index('--eval') + 1]) if '--eval' in args else load_eval(C)
P = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "query_parses.json")))
print(f"corpus {len(C.ids)} items | queries {len(Q)}")
DM = (C.info == "ok") if GATE else np.ones(len(C.ids), bool)
print("dense restricted to info-ok items:", int(DM.sum()))

reranker = None
if RERANK:
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    reranker = TextCrossEncoder(model_name=RERANK, threads=os.cpu_count())


def do_rerank(query, ranked, depth=50):
    head = ranked[:depth]
    docs = [C.text(n, "cap_tags_creator") for n in head]
    s = list(reranker.rerank(query, docs, batch_size=16))
    order = [head[i] for i in np.argsort(-np.array(s))]
    return order + ranked[depth:]


results, timing = {}, {}
for q in Q:
    m, rel = q["mask"], q["rel_rows"]
    runs = {}
    if q["examples"]:
        ex = q["example_rows"]
        cen = C.V[ex].mean(0)
        cen /= np.linalg.norm(cen)
        d = rank(C.V @ cen, m & DM, ex)
        extext = " ".join(C.text(n, "full") for n in ex)
        b = rank(C.bm25(extext, "full"), m, ex)
        runs["dense"] = runs["dense_parsed"] = d
        runs["bm25"] = runs["bm25_full"] = runs["bm25_parsed"] = b
        runs["hybrid"] = runs["hybrid_parsed"] = rrf(d, b)
        if reranker:
            # rerank against the example's own text
            runs["hybrid_parsed_rerank"] = do_rerank(C.text(ex[0], "cap_tags_creator")[:500], runs["hybrid_parsed"])
    else:
        text = q["query"]
        p = P[q["id"]]
        with Timer() as t:
            d = rank(C.dense([text]), m & DM)
        timing.setdefault("dense", []).append(t.s)
        with Timer() as t:
            b = rank(C.bm25(text, "cap_tags"), m)
        timing.setdefault("bm25", []).append(t.s)
        bf = rank(C.bm25(text, "full"), m)
        runs["dense"], runs["bm25"], runs["bm25_full"] = d, b, bf
        runs["hybrid"] = rrf(d, bf)
        dp = rank(C.dense([text] + p["phrases"]), m & DM)
        bp = rank(C.bm25(" ".join([text] + p["keywords"]), "full"), m)
        runs["dense_parsed"], runs["bm25_parsed"] = dp, bp
        runs["hybrid_parsed"] = rrf(dp, bp)
        if reranker:
            with Timer() as t:
                runs["hybrid_parsed_rerank"] = do_rerank(text, runs["hybrid_parsed"])
            timing.setdefault("rerank50", []).append(t.s)
    results[q["id"]] = {k: metrics(v, rel) for k, v in runs.items()}
    results[q["id"]]["_top10"] = {k: [C.code[n] for n in v[:10]] for k, v in runs.items()}

methods = [k for k in next(iter(results.values())) if not k.startswith("_")]
fam = {q["id"]: ("more_like_this" if q["examples"] else "text") for q in Q}
print(f"\n{'query':22s} " + " ".join(f"{m[:14]:>14s}" for m in methods) + "   (nDCG@10)")
for q in Q:
    r = results[q["id"]]
    print(f"{q['id']:22s} " + " ".join(f"{r[m]['ndcg10']:14.2f}" for m in methods) + f"   n_rel={len(q['rel_rows'])}")
for f in ("text", "more_like_this"):
    ids = [q["id"] for q in Q if fam[q["id"]] == f]
    print(f"\n== {f} ({len(ids)} queries) means")
    for key in ("ndcg10", "p10", "r20", "r100", "r100_conf", "mrr"):
        vals = []
        for m in methods:
            xs = [results[i][m][key] for i in ids if results[i][m][key] is not None]
            vals.append(np.mean(xs))
        print(f"  {key:10s} " + " ".join(f"{v:14.3f}" for v in vals))
print("\nlatency (s, mean per query):", {k: round(float(np.mean(v)), 4) for k, v in timing.items()})
json.dump({"results": results, "timing": {k: float(np.mean(v)) for k, v in timing.items()}},
          open(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"results_{TAG}.json"), "w"), indent=1)
