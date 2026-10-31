"""PROTOTYPE ONLY - EVALUATOR SIDE. Scores an experiment that has several repeats against same-repeat bases.

Only the evaluator role runs this file (it reads data/evals/labels/ through score_run.load_labels).

Given a list of (run, base) pairs (repeat k of the experiment against repeat k of the base), reports:
- mean nDCG@10 over repeats, with the range and a bootstrap CI over queries of the repeat-averaged
  per-query nDCG@10, for the runs and for the bases;
- mean P@10, MRR, R@100, success@5, unjudged10 over repeats;
- per-kind nDCG@10 and R@100 (mean over repeats);
- the single-answer group (hk_tailor, instant_pot, gun_trend) mean nDCG@10 / MRR / R@100;
- the paired delta: each query's delta is averaged over the repeats first, then a 2000-sample bootstrap
  95% CI over queries and W/L/T (|delta| > 0.005); the same for R@100;
- per-repeat deltas (mean only) for the record.

usage:
  python experiments/eval/score_multi.py --pair RUN1.json BASE1.json --pair RUN2.json BASE2.json ... \
      [--split dev] [--name NAME] [--json OUT.json] [--detail DETAIL.json]

--json gets aggregates only; --detail (put it under data/eval_work/) also gets per-query mean deltas.
"""
import argparse
import collections
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score_run import boot_ci, load_labels, score

SINGLE = ("hk_tailor", "instant_pot", "gun_trend")
KEYS = ["ndcg10", "p10", "mrr", "r100", "success5", "unjudged10"]


def paired(dq, n=2000, seed=1):
    d = np.array(dq)
    rng = np.random.default_rng(seed)
    bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(n)]
    return {"delta": round(float(d.mean()), 3),
            "ci95": [round(float(np.percentile(bs, 2.5)), 3), round(float(np.percentile(bs, 97.5)), 3)],
            "wins": int((d > 0.005).sum()), "losses": int((d < -0.005).sum()), "ties": int((abs(d) <= 0.005).sum())}


def agg(pers, L):
    """pers: list of per-query dicts (one per repeat). Returns mean-over-repeats aggregates."""
    qs = sorted(set.intersection(*[set(p) for p in pers]))
    out = {}
    rep_means = {k: [float(np.mean([p[q][k] for q in qs])) for p in pers] for k in KEYS}
    for k in KEYS:
        out[k] = round(float(np.mean(rep_means[k])), 3)
    out["ndcg10_per_repeat"] = [round(v, 3) for v in rep_means["ndcg10"]]
    qmean = [float(np.mean([p[q]["ndcg10"] for p in pers])) for q in qs]
    out["ndcg10_ci95"] = [round(v, 3) for v in boot_ci(qmean)]
    out["ndcg10_range"] = [round(min(rep_means["ndcg10"]), 3), round(max(rep_means["ndcg10"]), 3)]
    out["r100_per_repeat"] = [round(v, 3) for v in rep_means["r100"]]
    for m in ("ndcg10", "r100"):
        bk = collections.defaultdict(list)
        for q in qs:
            bk[L[q]["kinds"][0]].append(float(np.mean([p[q][m] for p in pers])))
        out[f"{m}_by_kind"] = {k: round(float(np.mean(v)), 3) for k, v in sorted(bk.items())}
    out["kind_counts"] = dict(sorted(collections.Counter(L[q]["kinds"][0] for q in qs).items()))
    sq = [q for q in SINGLE if q in qs]
    for m in ("ndcg10", "mrr", "r100"):
        out[f"single_{m}"] = round(float(np.mean([np.mean([p[q][m] for p in pers]) for q in sq])), 3) if sq else None
    out["n_queries"] = len(qs)
    out["n_repeats"] = len(pers)
    return out, qs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", nargs=2, action="append", required=True, metavar=("RUN", "BASE"))
    ap.add_argument("--split", default="dev")
    ap.add_argument("--name", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--detail", default=None)
    a = ap.parse_args()
    L = load_labels(a.split)
    cache = {}

    def sc(path):
        if path not in cache:
            with open(path) as f:
                cache[path] = score(json.load(f), L)
        return cache[path]

    runs = [sc(r) for r, _ in a.pair]
    bases = [sc(b) for _, b in a.pair]
    ra, qs = agg(runs, L)
    ba, _ = agg(bases, L)
    rep = {"name": a.name or os.path.basename(a.pair[0][0]), "split": a.split,
           "pairs": [[os.path.basename(r), os.path.basename(b)] for r, b in a.pair],
           "run": ra, "base": ba}
    detail = {}
    for m in ("ndcg10", "r100"):
        dq = {q: float(np.mean([runs[k][q][m] - bases[k][q][m] for k in range(len(runs))])) for q in qs}
        rep[f"delta_{m}"] = paired(list(dq.values()))
        rep[f"delta_{m}_per_repeat"] = [round(float(np.mean([runs[k][q][m] - bases[k][q][m] for q in qs])), 3)
                                        for k in range(len(runs))]
        detail[m] = {q: round(v, 4) for q, v in dq.items()}
    print(json.dumps(rep, indent=1))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(rep, f, indent=1)
    if a.detail:
        with open(a.detail, "w") as f:
            json.dump({"report": rep, "per_query_mean_delta": detail}, f, indent=1)


if __name__ == "__main__":
    main()
