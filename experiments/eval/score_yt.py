"""PROTOTYPE ONLY - EVALUATOR SIDE. Round-3 (YouTube) scorer for repeated runs.

Only the evaluator role runs this file (it reads $DIGESTER_DATA/evals/labels/).

Differences from score_run.py / score_multi.py (which assume the Instagram eval):
- adds R@10 and R@50 (standard recall, hits / |relevant|) and a capped recall
  R@k_cap = hits / min(|relevant|, k), because several YouTube searches have thousands of answers;
- per-kind results count a search under EVERY kind it carries (not only the first);
- codes that are not in the library (e.g. outside-library more-like-this examples leaking into other
  searches) count as non-relevant and are reported as `nonlib10` (share of the top 10);
- `--labels` picks the label file, so seed-only and pooled qrels can be scored side by side;
- run groups are given as stems (data/yt/runs/<stem>_r{1,2,3}.json); each comparison pairs repeat k
  with repeat k of the base, averages each search's delta over the repeats, then bootstraps over searches.

usage:
  python experiments/eval/score_yt.py --split dev --labels PATH --out OUT.json [--detail DETAIL.json]
      [--runs a0 a1 ...] [--cmp RUN:BASE ...]
--out gets aggregates only; put --detail (per-search numbers) under data/.
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

RUNS = os.path.join(DATA, "runs")
METRICS = ["ndcg10", "r10", "r50", "mrr", "p10", "r10_cap", "r50_cap", "success5", "r100", "unjudged10", "nonlib10"]
REPEATS = (1, 2, 3)

_LIB = None


def library():
    global _LIB
    if _LIB is None:
        _LIB = set()
        for line in open(os.path.join(DATA, "corpus", "items.jsonl"), encoding="utf-8"):
            _LIB.add(json.loads(line)["dedup_key"].split(":", 1)[1])
    return _LIB


def load_labels(path, split):
    keep = None
    if split in ("dev", "test"):
        keep = set(json.load(open(os.path.join(DATA, "evals", "split.json")))[split])
    L = {}
    for line in open(path):
        q = json.loads(line)
        if keep is not None and q["id"] not in keep:
            continue
        rel = {c: int(g) for c, g in q["relevant"].items() if g > 0}
        judged = set(q["relevant"]) | set(q.get("hard_negatives", [])) | set(q.get("judged_not_relevant", []))
        L[q["id"]] = {"rel": rel, "judged": judged, "kinds": q["kinds"]}
    return L


def score_one(ranked, rel, judged):
    lib = library()
    gains = [rel.get(c, 0) for c in ranked[:10]]
    dcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sorted(rel.values(), reverse=True)[:10]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    pos = {}
    for i, c in enumerate(ranked):
        pos.setdefault(c, i)
    first = min((pos[c] for c in rel if c in pos), default=None)
    hits = lambda k: sum(1 for c in rel if pos.get(c, 1e9) < k)  # noqa: E731
    n = len(rel)
    return {
        "ndcg10": dcg / idcg if idcg else 0.0,
        "r10": hits(10) / n, "r50": hits(50) / n, "r100": hits(100) / n,
        "r10_cap": hits(10) / min(n, 10), "r50_cap": hits(50) / min(n, 50),
        "mrr": 1.0 / (first + 1) if first is not None else 0.0,
        "p10": sum(1 for c in ranked[:10] if c in rel) / 10,
        "success5": float(any(c in rel for c in ranked[:5])),
        "unjudged10": sum(1 for c in ranked[:10] if c not in judged and c in lib) / 10,
        "nonlib10": sum(1 for c in ranked[:10] if c not in lib) / 10,
    }


def score_file(path, L):
    run = json.load(open(path))
    return {q: score_one(run["queries"].get(q, []), lab["rel"], lab["judged"]) for q, lab in L.items() if lab["rel"]}


def boot(vals, n=2000, seed=1):
    v = np.array(vals, dtype=float)
    rng = np.random.default_rng(seed)
    bs = v[rng.integers(0, len(v), (n, len(v)))].mean(axis=1)
    return [round(float(np.percentile(bs, 2.5)), 3), round(float(np.percentile(bs, 97.5)), 3)]


def group(stem, L, cache):
    reps = []
    for k in REPEATS:
        p = os.path.join(RUNS, f"{stem}_r{k}.json")
        if p not in cache:
            cache[p] = score_file(p, L)
        reps.append(cache[p])
    return reps


def summarise(reps, L):
    qs = sorted(reps[0])
    out = {"n_searches": len(qs)}
    for m in METRICS:
        per_rep = [float(np.mean([r[q][m] for q in qs])) for r in reps]
        out[m] = round(float(np.mean(per_rep)), 3)
        out[m + "_reps"] = [round(x, 3) for x in per_rep]
    qmean = [float(np.mean([r[q]["ndcg10"] for r in reps])) for q in qs]
    out["ndcg10_ci95"] = boot(qmean, seed=0)
    out["ndcg10_spread"] = round(max(out["ndcg10_reps"]) - min(out["ndcg10_reps"]), 3)
    out["ndcg10_sd_reps"] = round(float(np.std(out["ndcg10_reps"], ddof=1)), 3)
    bk = collections.defaultdict(list)
    for q in qs:
        for kd in L[q]["kinds"]:
            bk[kd].append(q)
    out["by_kind"] = {kd: {"n": len(v), **{m: round(float(np.mean([np.mean([r[q][m] for r in reps]) for q in v])), 3)
                                            for m in ("ndcg10", "r10", "r50", "mrr")}}
                      for kd, v in sorted(bk.items())}
    return out


def compare(run_reps, base_reps, L):
    qs = sorted(run_reps[0])
    res = {}
    for m in ("ndcg10", "r50", "mrr"):
        d = np.array([np.mean([run_reps[k][q][m] - base_reps[k][q][m] for k in range(len(REPEATS))]) for q in qs])
        res[m] = {"delta": round(float(d.mean()), 3), "ci95": boot(d), "wins": int((d > 0.005).sum()),
                  "losses": int((d < -0.005).sum()), "ties": int((abs(d) <= 0.005).sum()),
                  "per_repeat": [round(float(np.mean([run_reps[k][q][m] - base_reps[k][q][m] for q in qs])), 3)
                                 for k in range(len(REPEATS))]}
    bk = collections.defaultdict(list)
    for q in qs:
        for kd in L[q]["kinds"]:
            bk[kd].append(float(np.mean([run_reps[k][q]["ndcg10"] - base_reps[k][q]["ndcg10"] for k in range(3)])))
    res["ndcg10_by_kind"] = {kd: {"n": len(v), "delta": round(float(np.mean(v)), 3)} for kd, v in sorted(bk.items())}
    return res


def per_search(reps):
    return {q: {m: round(float(np.mean([r[q][m] for r in reps])), 4) for m in ("ndcg10", "r50", "mrr", "unjudged10")}
            for q in sorted(reps[0])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--labels", default=os.path.join(DATA, "evals", "labels", "evalset.jsonl"))
    ap.add_argument("--runs", nargs="*", default=[])
    ap.add_argument("--cmp", nargs="*", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--detail", default=None)
    a = ap.parse_args()
    L = load_labels(a.labels, a.split)
    cache = {}
    stems = list(dict.fromkeys(a.runs + [s for c in a.cmp for s in c.split(":")]))
    rep = {"split": a.split, "labels": os.path.basename(a.labels), "runs": {}, "comparisons": {}}
    detail = {}
    for s in stems:
        g = group(s, L, cache)
        rep["runs"][s] = summarise(g, L)
        detail[s] = per_search(g)
    for c in a.cmp:
        r, b = c.split(":")
        rep["comparisons"][c] = compare(group(r, L, cache), group(b, L, cache), L)
    json.dump(rep, open(a.out, "w"), indent=1)
    if a.detail:
        json.dump(detail, open(a.detail, "w"), indent=1)
    for s, v in rep["runs"].items():
        print(f"{s:30s} nDCG {v['ndcg10']:.3f} {v['ndcg10_ci95']} spread {v['ndcg10_spread']:.3f} R10 {v['r10']:.3f} "
              f"R50 {v['r50']:.3f} MRR {v['mrr']:.3f} P10 {v['p10']:.3f} unj {v['unjudged10']:.2f} nonlib {v['nonlib10']:.3f}")
    for c, v in rep["comparisons"].items():
        d = v["ndcg10"]
        print(f"{c:50s} d {d['delta']:+.3f} {d['ci95']} W/L/T {d['wins']}/{d['losses']}/{d['ties']} reps {d['per_repeat']}")


if __name__ == "__main__":
    main()
