"""PROTOTYPE ONLY - EVALUATOR SIDE. Round-4 (combined Instagram + YouTube) scorer for repeated runs.

Only the evaluator role runs this file (it reads $DIGESTER_DATA/evals/labels/).

Adapted from score_yt.py for the combined root (DIGESTER_DATA=data/all):
- every summary is given overall and per `scope` (ig | yt) of the search;
- a run may cover only some searches (the per-platform controls): each run is scored on the searches it has;
  comparisons use the searches both runs have;
- `cross10` = share of a search's top 10 from the OTHER platform; `cross_rel10` = how many of those are
  labelled relevant (count per search); `cross_unj10` = how many are unjudged;
- `--pool OUT.json` writes the union of unjudged in-library top-10 codes over all given runs and repeats
  ({search_id: [codes]}) for blind judging;
- metrics: nDCG@10, R@10, R@50, MRR, P@10, success@5, R@100, capped recall, unjudged10, nonlib10.
- round 8 (see results/validation-audit.md): any split in split.json (plus `known_test_clean`) is honoured; known-item
  metrics `mrr2` / `s10_2` use only the grade-2 target; `success10` = any relevant item in the top 10.
- round 9 (BRIEF-9): `--gains` picks the nDCG gain: `exp2` (default, 2^g - 1, as in rounds 1-8), `lin4` (gain = grade,
  0/1/2/3 for the 4-point scale) or `col3` (4-point grades collapsed 3, 2 -> 2, then 2^g - 1: comparable with old
  3-point labels). Only nDCG changes; mrr2 / s10_2 still count grade >= 2.
- milestone (round 4): the `test` split's label rows use `judged_nonrelevant` (Derrick's gold zeros) and may have
  scope `both` (no own platform, so cross10 = 0); `unvetted_candidates` are left unjudged; a `both` subset is reported.

usage:
  python experiments/eval/score_c4.py --rundir PATH --split dev --labels PATH --out OUT.json
      [--detail DETAIL.json] [--runs c0 c1 ...] [--cmp RUN:BASE ...] [--pool POOL.json]
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

METRICS = ["ndcg10", "r10", "r50", "mrr", "p10", "success5", "r100", "r10_cap", "r50_cap",
           "unjudged10", "nonlib10", "cross10", "cross_rel10", "cross_unj10",
           "mrr2", "success10", "s10_2"]  # changed in round 8, see audit: grade-2-only known-item metrics
REPEATS = (1, 2, 3)
SCOPE_PLAT = {"ig": "instagram", "yt": "youtube", "both": None}
SCOPES = ("all", "ig", "yt", "both")

_PLAT = None
GAINS = "exp2"  # round 9: set by --gains (exp2 | lin4 | col3)


def gain(g):
    if GAINS == "lin4":
        return float(g)
    if GAINS == "col3":
        g = min(g, 2)
    return 2.0 ** g - 1


def platforms():
    global _PLAT
    if _PLAT is None:
        _PLAT = {}
        for line in open(os.path.join(DATA, "corpus", "items.jsonl"), encoding="utf-8"):
            it = json.loads(line)
            _PLAT[it["dedup_key"].split(":", 1)[1]] = it["platform"]
    return _PLAT


def load_labels(path, split):
    keep = None
    # changed in round 8, see audit: any split named in split.json is honoured (known_dev, ig_known_dev, ...);
    # before, an unknown split name silently scored every search the run contains.
    splits = json.load(open(os.path.join(DATA, "evals", "split.json")))
    if split == "known_test_clean":  # session-disjoint known_test subset (evaluator-only id list)
        keep = set(json.load(open(os.path.join(os.path.dirname(path), "known_test_clean_ids.json")))["ids"])
    elif split in splits and split != "_note":
        keep = set(splits[split])
    elif split != "all":
        raise SystemExit(f"unknown split {split!r}; use one in split.json, known_test_clean or all")
    L = {}
    for line in open(path):
        q = json.loads(line)
        if keep is None or q["id"] not in keep:
            continue
        rel = {c: int(g) for c, g in q["relevant"].items() if g > 0}
        judged = (set(q["relevant"]) | set(q.get("hard_negatives", [])) | set(q.get("judged_not_relevant", []))
                  | set(q.get("judged_nonrelevant", [])))
        L[q["id"]] = {"rel": rel, "judged": judged, "kinds": q["kinds"], "scope": q["scope"]}
    return L


def score_one(ranked, lab):
    rel, judged = lab["rel"], lab["judged"]
    plat = platforms()
    own = SCOPE_PLAT[lab["scope"]]
    top = ranked[:10]
    gains = [rel.get(c, 0) for c in top]
    dcg = sum(gain(g) / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sorted(rel.values(), reverse=True)[:10]
    idcg = sum(gain(g) / math.log2(i + 2) for i, g in enumerate(ideal))
    pos = {}
    for i, c in enumerate(ranked):
        pos.setdefault(c, i)
    first = min((pos[c] for c in rel if c in pos), default=None)
    first2 = min((pos[c] for c, g in rel.items() if g >= 2 and c in pos), default=None)
    hits = lambda k: sum(1 for c in rel if pos.get(c, 1e9) < k)  # noqa: E731
    n = len(rel)
    cross = [c for c in top if own and c in plat and plat[c] != own]
    return {
        "ndcg10": dcg / idcg if idcg else 0.0,
        "r10": hits(10) / n, "r50": hits(50) / n, "r100": hits(100) / n,
        "r10_cap": hits(10) / min(n, 10), "r50_cap": hits(50) / min(n, 50),
        "mrr": 1.0 / (first + 1) if first is not None else 0.0,
        "p10": sum(1 for c in top if c in rel) / 10,
        "success5": float(any(c in rel for c in ranked[:5])),
        "unjudged10": sum(1 for c in top if c not in judged and c in plat) / 10,
        "nonlib10": sum(1 for c in top if c not in plat) / 10,
        "cross10": len(cross) / 10,
        "cross_rel10": float(sum(1 for c in cross if c in rel)),
        "cross_unj10": float(sum(1 for c in cross if c not in judged)),
        # changed in round 8, see audit: known-item metrics count only the grade-2 target (the first video watched);
        # `mrr` above also counts grade-1 later videos, which are mostly autoplay / unrelated watches.
        "mrr2": 1.0 / (first2 + 1) if first2 is not None else 0.0,
        "success10": float(any(c in rel for c in top)),
        "s10_2": float(first2 is not None and first2 < 10),
    }


def boot(vals, n=2000, seed=1):
    v = np.array(vals, dtype=float)
    rng = np.random.default_rng(seed)
    bs = v[rng.integers(0, len(v), (n, len(v)))].mean(axis=1)
    return [round(float(np.percentile(bs, 2.5)), 3), round(float(np.percentile(bs, 97.5)), 3)]


class Runs:
    def __init__(self, rundir, L):
        self.rundir, self.L, self.cache, self.raw = rundir, L, {}, {}

    def reps(self, stem):
        out = []
        for k in REPEATS:
            p = os.path.join(self.rundir, f"{stem}_r{k}.json")
            if p not in self.cache:
                run = json.load(open(p))
                self.raw[p] = run["queries"]
                self.cache[p] = {q: score_one(run["queries"][q], lab) for q, lab in self.L.items()
                                 if lab["rel"] and q in run["queries"]}
            out.append(self.cache[p])
        return out


def subsets(qs, L):
    return {"all": qs, **{sc: [q for q in qs if L[q]["scope"] == sc] for sc in SCOPES[1:]}}


def summ(reps, qs, L):
    out = {"n_searches": len(qs)}
    if not qs:
        return out
    for m in METRICS:
        per_rep = [float(np.mean([r[q][m] for q in qs])) for r in reps]
        out[m] = round(float(np.mean(per_rep)), 3)
        out[m + "_reps"] = [round(x, 3) for x in per_rep]
    qmean = [float(np.mean([r[q]["ndcg10"] for r in reps])) for q in qs]
    out["ndcg10_ci95"] = boot(qmean, seed=0)
    out["ndcg10_spread"] = round(max(out["ndcg10_reps"]) - min(out["ndcg10_reps"]), 3)
    bk = collections.defaultdict(list)
    for q in qs:
        for kd in L[q]["kinds"]:
            bk[kd].append(q)
    out["by_kind"] = {kd: {"n": len(v), **{m: round(float(np.mean([np.mean([r[q][m] for r in reps]) for q in v])), 3)
                                            for m in ("ndcg10", "r10", "r50", "mrr", "cross10")}}
                      for kd, v in sorted(bk.items())}
    return out


def summarise(reps, L):
    qs = sorted(reps[0])
    return {s: summ(reps, v, L) for s, v in subsets(qs, L).items()}


def cmp_one(run_reps, base_reps, qs, L):
    res = {"n": len(qs)}
    if not qs:
        return res
    for m in ("ndcg10", "r10", "r50", "mrr", "mrr2", "s10_2"):
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


def compare(run_reps, base_reps, L):
    qs = sorted(set(run_reps[0]) & set(base_reps[0]))
    return {s: cmp_one(run_reps, base_reps, v, L) for s, v in subsets(qs, L).items()}


def per_search(reps):
    return {q: {m: round(float(np.mean([r[q][m] for r in reps])), 4)
                for m in ("ndcg10", "r10", "r50", "mrr", "mrr2", "s10_2", "unjudged10", "cross10", "cross_rel10")}
            for q in sorted(reps[0])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rundir", default=os.path.join(DATA, "runs", "r4.1"))
    ap.add_argument("--split", default="dev")
    ap.add_argument("--labels", default=os.path.join(DATA, "evals", "labels", "evalset.jsonl"))
    ap.add_argument("--runs", nargs="*", default=[])
    ap.add_argument("--cmp", nargs="*", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--detail", default=None)
    ap.add_argument("--pool", default=None)
    ap.add_argument("--gains", default="exp2", choices=["exp2", "lin4", "col3"])  # round 9
    a = ap.parse_args()
    global GAINS
    GAINS = a.gains
    L = load_labels(a.labels, a.split)
    R = Runs(a.rundir, L)
    stems = list(dict.fromkeys(a.runs + [s for c in a.cmp for s in c.split(":")]))
    rep = {"split": a.split, "labels": os.path.basename(a.labels), "gains": a.gains, "runs": {}, "comparisons": {}}
    detail = {}
    for s in stems:
        g = R.reps(s)
        rep["runs"][s] = summarise(g, L)
        detail[s] = per_search(g)
    for c in a.cmp:
        r, b = c.split(":")
        rep["comparisons"][c] = compare(R.reps(r), R.reps(b), L)
    json.dump(rep, open(a.out, "w"), indent=1)
    if a.detail:
        json.dump(detail, open(a.detail, "w"), indent=1)
    if a.pool:
        plat = platforms()
        pool = collections.defaultdict(set)
        for p, queries in R.raw.items():
            for q, ranked in queries.items():
                if q in L:
                    for c in ranked[:10]:
                        if c in plat and c not in L[q]["judged"]:
                            pool[q].add(c)
        json.dump({q: sorted(v) for q, v in sorted(pool.items())}, open(a.pool, "w"))
        print(f"pool: {sum(len(v) for v in pool.values())} items over {len(pool)} searches -> {a.pool}")
    for s, v in rep["runs"].items():
        line = [f"{s:8s}"]
        for sc in SCOPES:
            x = v[sc]
            if x["n_searches"]:
                line.append(f"{sc}[{x['n_searches']}] nDCG {x['ndcg10']:.3f} sp {x['ndcg10_spread']:.3f} "
                            f"R10 {x['r10']:.3f} R50 {x['r50']:.3f} MRR {x['mrr']:.3f} unj {x['unjudged10']:.2f} "
                            f"x {x['cross10']:.2f}")
        print(" | ".join(line))
    for c, v in rep["comparisons"].items():
        line = [f"{c:12s}"]
        for sc in SCOPES:
            if v[sc]["n"]:
                d = v[sc]["ndcg10"]
                line.append(f"{sc} {d['delta']:+.3f} {d['ci95']} {d['wins']}/{d['losses']}/{d['ties']}")
        print(" | ".join(line))


if __name__ == "__main__":
    main()
