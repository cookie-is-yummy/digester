"""PROTOTYPE ONLY - EVALUATOR SIDE. Scores run files against the labels.

Only the evaluator role runs this file or opens data/evals/labels/. The experimenter gets back the
aggregate report, not per-item labels.

A run file is {"method", "embedding", "meta", "queries": {query_id: [content_code, ...]}} (see lib/corpus.py write_run).

Every item in the export counts, including items with no caption: a method that can't reach them scores lower.

Metrics, averaged over queries:
- ndcg10: graded (2 = confirmed, 1 = borderline)
- p10
- success5: any right answer in the top 5; the Gate 1 metric in docs/08
- mrr
- r100: recall at 100
- unjudged10: share of the top 10 with no label; above ~0.15 means pool and judge before trusting ndcg

usage:
  python experiments/eval/score_run.py RUN.json [--split dev|test|all] [--vs BASE.json] [--json OUT.json] [--pool POOL.json]
"""
import argparse
import collections
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from corpus import DATA  # noqa: E402

LABELS = os.path.join(DATA, "evals", "labels", "evalset.jsonl")


def load_labels(split):
    items = {}
    for line in open(os.path.join(DATA, "corpus", "items.jsonl"), encoding="utf-8"):
        it = json.loads(line)
        items[it["dedup_key"].split(":", 1)[1]] = it
    keep = None
    if split in ("dev", "test"):
        keep = set(json.load(open(os.path.join(DATA, "evals", "split.json")))[split])
    L = {}
    for line in open(LABELS):
        q = json.loads(line)
        if keep is not None and q["id"] not in keep:
            continue
        f = q["filters"]

        def passes(c):
            it = items.get(c)
            if it is None:
                return False
            if f.get("before") and (it.get("first_seen_at") or "9999") >= f["before"]:
                return False
            if f.get("kinds") and not set(it["interaction_kinds"]) & set(f["kinds"]):
                return False
            return True

        rel = {c: g for c, g in q["relevant"].items() if g > 0 and passes(c)}
        judged = set(q["relevant"]) | set(q.get("hard_negatives", [])) | set(q.get("judged_not_relevant", []))
        L[q["id"]] = {"rel": rel, "judged": judged, "kinds": q["kinds"], "query": q["query"]}
    return L


def score_one(ranked, rel, judged, k=10):
    gains = [rel.get(c, 0) for c in ranked[:k]]
    dcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sorted(rel.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    pos = {c: i for i, c in enumerate(ranked)}
    first = min((pos[c] for c in rel if c in pos), default=None)
    return {
        "ndcg10": dcg / idcg if idcg else 0.0,
        "p10": sum(1 for c in ranked[:10] if c in rel) / 10,
        "success5": float(any(c in rel for c in ranked[:5])),
        "mrr": 1.0 / (first + 1) if first is not None else 0.0,
        "r100": sum(1 for c in rel if pos.get(c, 1e9) < 100) / len(rel),
        "unjudged10": sum(1 for c in ranked[:10] if c not in judged) / 10,
    }


def score(run, L):
    per = {}
    for qid, lab in L.items():
        if not lab["rel"]:
            continue
        per[qid] = score_one(run["queries"].get(qid, []), lab["rel"], lab["judged"])
    return per


def boot_ci(vals, n=2000, seed=0):
    rng = np.random.default_rng(seed)
    v = np.array(vals)
    means = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(n)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--vs", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--pool", default=None, help="append unjudged top-10 items to this pool file for judging")
    a = ap.parse_args()
    L = load_labels(a.split)
    run = json.load(open(a.run))
    per = score(run, L)
    keys = ["ndcg10", "p10", "success5", "mrr", "r100", "unjudged10"]
    agg = {k: float(np.mean([p[k] for p in per.values()])) for k in keys}
    ci = boot_ci([p["ndcg10"] for p in per.values()])
    by_kind = collections.defaultdict(list)
    for q, p in per.items():
        by_kind[L[q]["kinds"][0]].append(p["ndcg10"])
    rep = {"run": os.path.basename(a.run), "method": run.get("method"), "split": a.split, "n_queries": len(per),
           **{k: round(v, 3) for k, v in agg.items()}, "ndcg10_ci95": [round(ci[0], 3), round(ci[1], 3)],
           "ndcg10_by_kind": {k: round(float(np.mean(v)), 3) for k, v in sorted(by_kind.items())},
           "meta": run.get("meta", {})}
    if a.vs:
        base = score(json.load(open(a.vs)), L)
        d = np.array([per[q]["ndcg10"] - base[q]["ndcg10"] for q in per if q in base])
        rng = np.random.default_rng(1)
        bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(2000)]
        rep["vs"] = {"base": os.path.basename(a.vs), "delta_ndcg10": round(float(d.mean()), 3),
                     "delta_ci95": [round(float(np.percentile(bs, 2.5)), 3), round(float(np.percentile(bs, 97.5)), 3)],
                     "wins": int((d > 0.005).sum()), "losses": int((d < -0.005).sum()), "ties": int((abs(d) <= 0.005).sum())}
    if a.pool:
        pool = json.load(open(a.pool)) if os.path.exists(a.pool) else {}
        for q in per:
            for c in run["queries"].get(q, [])[:10]:
                if c not in L[q]["judged"]:
                    pool.setdefault(q, [])
                    if c not in pool[q]:
                        pool[q].append(c)
        json.dump(pool, open(a.pool, "w"), indent=1)
        rep["pooled_unjudged"] = sum(len(v) for v in pool.values())
    print(json.dumps(rep, indent=1))
    if a.json:
        json.dump(rep, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
