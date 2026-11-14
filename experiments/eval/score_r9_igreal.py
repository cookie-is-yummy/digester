"""PROTOTYPE ONLY - EVALUATOR SIDE. Round-9 Phase 0: score H0r8, Q8 and FM on `ig_real` (Derrick's 31 real
Instagram searches), each slice (`search_kind`) separately, with the round-8 reporting rules plus A-005.

Reads $DIGESTER_DATA/evals/labels/ (evaluator only). Writes aggregates to --out (no texts, no codes, no per-search
numbers) and per-search numbers to --detail under data/.

Slices:
- known_item: mrr2 / s10_2 on the target only (seed labels, no pooling); any-grade mrr / success10 secondary.
- topic, meta: target = 3, pooled top-10 items graded by the two-judge harness (judges9.py, rule = lower grade);
  nDCG@10 with gains 0/1/2/3 (`lin4`, primary) and the collapsed 3-point version (`col3`: 3, 2 -> 2, gains 2^g - 1).
Label variants (topic / meta): `low` (merged evalset, primary), `high` (sensitivity: the higher judge grade),
`g1to0` (this round's grade-1 items set to 0), `seed` (Derrick's targets only, labels/ig_real.jsonl).
Stats: paired delta (mean over the 3 repeats per search), bootstrap 95% CI, W/L/T (|d| > 0.005), sd_d,
MDE = (t_.975 + t_.80) * sd_d / sqrt(n), one-sided paired t-test for a gain, Holm over the 3 comparisons per slice
and metric (FM - H0r8, Q8 - H0r8, FM - Q8).

usage: score_r9_igreal.py --sheet SHEET.jsonl --high GRADES_HIGH.json --out OUT.json --detail DETAIL.json
"""
import argparse
import copy
import json
import os
import sys

import numpy as np
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score_c4 as sc  # noqa: E402

DATA = sc.DATA
LAB = os.path.join(DATA, "evals", "labels")
RUNDIR = os.path.join(DATA, "runs", "r9")
METHODS = {"H0r8": "h0r8_ig_real", "Q8": "q8_ig_real", "FM": "fm_ig_real"}
CMPS = [("Q8", "H0r8"), ("FM", "H0r8"), ("FM", "Q8")]


def read_rows(path, ids):
    return {q["id"]: q for q in map(json.loads, open(path)) if q["id"] in ids}


def to_lab(q):
    rel = {c: int(g) for c, g in q["relevant"].items() if g > 0}
    judged = set(q["relevant"]) | set(q.get("judged_not_relevant", [])) | set(q.get("judged_nonrelevant", []))
    return {"rel": rel, "judged": judged, "kinds": q["kinds"], "scope": q["scope"]}


def variants(ids, sheet_path, high_path):
    merged = read_rows(os.path.join(LAB, "evalset.jsonl"), ids)
    seed = read_rows(os.path.join(LAB, "ig_real.jsonl"), ids)
    sheet = [json.loads(x) for x in open(sheet_path) if x.strip()]
    high = json.load(open(high_path))
    this_round = {(r["query_id"], r["code"]) for r in sheet}
    low = {q: to_lab(r) for q, r in merged.items()}
    hi = copy.deepcopy(low)
    for r, g in zip(sheet, high):
        lab = hi[r["query_id"]]
        if g > 0:
            lab["rel"][r["code"]] = int(g)
        else:
            lab["rel"].pop(r["code"], None)
    g10 = copy.deepcopy(low)
    for (q, c) in this_round:
        if g10[q]["rel"].get(c) == 1:
            del g10[q]["rel"][c]
    sd = {q: to_lab(r) for q, r in seed.items()}
    return {"low": low, "high": hi, "g1to0": g10, "seed": sd}, this_round, merged


def per_rep(L, gains):
    sc.GAINS = gains
    out = {}
    for m, stem in METHODS.items():
        reps = []
        for k in sc.REPEATS:
            run = json.load(open(os.path.join(RUNDIR, f"{stem}_r{k}.json")))["queries"]
            d = {}
            for q, lab in L.items():
                ranked = run[q]
                s = sc.score_one(ranked, lab)
                s["good5"] = float(any(lab["rel"].get(c, 0) >= 2 for c in ranked[:5]))
                s["exact5"] = float(any(lab["rel"].get(c, 0) >= 3 for c in ranked[:5]))
                s["good_p10"] = sum(1 for c in ranked[:10] if lab["rel"].get(c, 0) >= 2) / 10
                d[q] = s
            reps.append(d)
        out[m] = reps
    return out


def qmean(reps, q, m):
    return float(np.mean([r[q][m] for r in reps]))


def mde(sd, n):
    if n < 2:
        return None
    t = stats.t.ppf(0.975, n - 1) + stats.t.ppf(0.80, n - 1)
    return round(float(t * sd / np.sqrt(n)), 3)


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: 2.0 if ps[i] is None else ps[i])
    adj, run = [None] * len(ps), 0.0
    for rank, i in enumerate(order):
        if ps[i] is None:
            continue
        run = max(run, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = run
    return adj


def block(R, qs, metrics):
    res = {"n": len(qs), "methods": {}, "comparisons": {}}
    if not qs:
        return res
    for m in METHODS:
        res["methods"][m] = {}
        for met in metrics:
            vals = [qmean(R[m], q, met) for q in qs]
            res["methods"][m][met] = {"mean": round(float(np.mean(vals)), 3),
                                      "ci95": sc.boot(vals, seed=0) if len(qs) > 1 else None,
                                      "reps": [round(float(np.mean([r[q][met] for q in qs])), 3) for r in R[m]]}
    for met in metrics:
        ps, rows = [], []
        for a, b in CMPS:
            d = np.array([qmean(R[a], q, met) - qmean(R[b], q, met) for q in qs])
            sd = float(d.std(ddof=1)) if len(d) > 1 else 0.0
            if len(d) > 1 and sd > 0:
                p = float(stats.ttest_1samp(d, 0.0, alternative="greater").pvalue)
            elif len(d) > 1:  # identical on every search: no evidence of a gain (or a constant gain)
                p = 0.0 if d.mean() > 0 else 1.0
            else:
                p = None
            ps.append(p)
            rows.append({"delta": round(float(d.mean()), 3), "ci95": sc.boot(d) if len(d) > 1 else None,
                         "wins": int((d > 0.005).sum()), "losses": int((d < -0.005).sum()),
                         "ties": int((abs(d) <= 0.005).sum()), "sd_d": round(sd, 3), "mde80": mde(sd, len(d)),
                         "p_one_sided": None if p is None else round(p, 4)})
        for (a, b), row, h in zip(CMPS, rows, holm(ps)):
            row["p_holm"] = None if h is None else round(h, 4)
            row["within_noise"] = bool(row["mde80"] is not None and abs(row["delta"]) < row["mde80"])
            res["comparisons"].setdefault(f"{a}-{b}", {})[met] = row
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--high", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--detail", required=True)
    a = ap.parse_args()
    ids = set(json.load(open(os.path.join(DATA, "evals", "split.json")))["ig_real"])
    V, this_round, merged = variants(ids, a.sheet, a.high)
    kind = {q: merged[q]["search_kind"] for q in ids}
    slices = {s: sorted(q for q in ids if kind[q] == s) for s in ("known_item", "topic", "meta")}
    slices["topic+meta"] = slices["topic"] + slices["meta"]
    slices["all"] = sorted(ids)
    rep = {"split": "ig_real", "scoring": "1 of 3", "round": "r9.0", "methods": METHODS,
           "slices_n": {s: len(v) for s, v in slices.items()}, "known_item": {}, "pooled": {}, "sensitivity": {}}
    detail = {}

    # known-item slice: seed labels only (targets), no pooling
    R = per_rep(V["seed"], "lin4")
    km = ["mrr2", "s10_2", "mrr", "success10"]
    rep["known_item"] = block(R, slices["known_item"], km)
    rep["target_only_all_slices"] = {s: block(R, slices[s], ["mrr2", "s10_2"]) for s in ("topic", "topic+meta", "all")}
    detail["seed"] = {m: {q: {k: round(qmean(R[m], q, k), 4) for k in km} for q in sorted(ids)} for m in METHODS}

    # topic / meta: pooled labels
    pm = ["ndcg10", "good5", "exact5", "success5", "p10", "good_p10", "unjudged10"]
    for var in ("low", "high", "g1to0", "seed"):
        for gains in ("lin4", "col3"):
            R = per_rep(V[var], gains)
            key = f"{var}_{gains}"
            out = {s: block(R, slices[s], pm if var == "low" else ["ndcg10", "good5", "unjudged10"])
                   for s in ("topic", "meta", "topic+meta")}
            if var == "low":
                rep["pooled"][gains] = out
            else:
                rep["sensitivity"][key] = out
            detail[key] = {m: {q: round(qmean(R[m], q, "ndcg10"), 4) for q in slices["topic+meta"]} for m in METHODS}

    # share of relevant top-10 items (topic+meta, primary labels) that rest on this round's grades
    tot = new = 0
    for stem in METHODS.values():
        for k in sc.REPEATS:
            run = json.load(open(os.path.join(RUNDIR, f"{stem}_r{k}.json")))["queries"]
            for q in slices["topic+meta"]:
                for c in run[q][:10]:
                    if V["low"][q]["rel"].get(c, 0) > 0:
                        tot += 1
                        new += (q, c) in this_round
    rep["relevant_top10_share_from_r9_0_grades"] = round(new / tot, 3) if tot else None

    # label inventory (aggregates)
    g = [V["low"][q]["rel"].get(c, 0) for (q, c) in this_round]
    rep["pooled_grades"] = {"items": len(this_round), "searches": len({q for q, _ in this_round}),
                            "dist4_lower_rule": {str(x): g.count(x) for x in range(4)},
                            "per_search_mean_relevant": round(float(np.mean(
                                [len(V["low"][q]["rel"]) for q in slices["topic+meta"]])), 2)}
    # cost / latency from run meta
    rep["cost_latency"] = {}
    for m, stem in METHODS.items():
        meta = json.load(open(os.path.join(RUNDIR, f"{stem}_r1.json")))["meta"]
        ps = meta["per_split"]["ig_real"]
        rep["cost_latency"][m] = {k: ps.get(k) for k in ("cost_per_1k_searches_usd", "total_p50_s", "total_p95_s",
                                                         "yt_share_top10_mean")}
        rep["cost_latency"][m]["paths"] = {k.split(":", 1)[1]: v for k, v in meta.get("counts", {}).items()
                                           if k.split(":", 1)[1] in ("instant", "rewrite", "refined_rewrite")}
    json.dump(rep, open(a.out, "w"), indent=1)
    json.dump(detail, open(a.detail, "w"), indent=1)
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
