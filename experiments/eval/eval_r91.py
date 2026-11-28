"""PROTOTYPE ONLY - EVALUATOR SIDE. Round 9.1 evaluation (BRIEF-9 Track 1 arms A1, A2; Track 2 arms M, M2) vs Q8.

Reads $DIGESTER_DATA/evals/labels/ (evaluator only). Writes aggregates to experiments/results/r9.1-eval.json and
per-search detail to $DIGESTER_DATA/eval_work/r9.1/ (gitignored). No paid calls.

Runs: eval_work/r9.1/runs/{q8,a1,a2,m,m2,q8ref}_r{1,2,3}.json; q8 = runs/r8.5/q8_r{k} + runs/r9/q8_facet_dev_r{k}
merged (q8ref, the Track-2 runner's reproduction, is identical 1,000 deep on all 602 searches).
Label variants (dev, facet_dev): pre (before r9.1 pooling), low (primary: two-judge lower grade, merged),
high (this round's items at the higher grade), g1zero (this round's 4-point grade-1 items -> 0), derrick (Derrick's
own grades only: dev = his 72 calibration grades, facet_dev = his target), noai (dev: r8.8's no-AI-grade file).
Stats: paired per-search delta = mean over 3 repeats; 95% bootstrap CI (score_c4.boot); W/L/T at |d| > 0.005;
MDE = (t.975 + t.80) sd_d / sqrt(n); one-sided paired t p; Holm over the 4 arms per set x metric x variant.
"""
import collections
import json
import os
import sys

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import score_c4 as sc  # noqa: E402

DATA = sc.DATA
LAB = os.path.join(DATA, "evals", "labels")
W = os.path.join(DATA, "eval_work", "r9.1")
RUNDIR = os.path.join(W, "runs")
ARMS = ["a1", "a2", "m", "m2"]
BASE = "q8"
ROUND_JUDGE = "r9.1 two-judge"
OUT_JSON = os.path.join(os.path.dirname(HERE), "results", "r9.1-eval.json")


def rows(path):
    return [json.loads(line) for line in open(path) if line.strip()]


def write_rows(rs, path):
    with open(path, "w") as f:
        for r in rs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def collapse(g):
    return min(g, 2)


# ---------------- label variants ----------------
def build_variants():
    sheet = rows(os.path.join(W, "sheet_r9.1.jsonl"))
    lo = json.load(open(os.path.join(W, "grades_r9.1_low.json")))
    hi = json.load(open(os.path.join(W, "grades_r9.1_high.json")))
    this = {(r["query_id"], r["code"]): (int(a), int(b)) for r, a, b in zip(sheet, lo, hi)}
    low = rows(os.path.join(LAB, "evalset.jsonl"))
    out = {"pre": os.path.join(LAB, "evalset.pre_r9.1.jsonl"), "low": os.path.join(LAB, "evalset.jsonl")}

    def variant(name, fn):
        rs = json.loads(json.dumps(low))
        for q in rs:
            for (qid, c), (a, b) in this.items():
                if qid != q["id"]:
                    continue
                q["relevant"].pop(c, None)
                if c in q.get("judged_not_relevant", []):
                    q["judged_not_relevant"].remove(c)
                g4 = fn(a, b)
                g = g4 if q.get("grade_scale") else collapse(g4)
                if g > 0:
                    q["relevant"][c] = g
                else:
                    q.setdefault("judged_not_relevant", []).append(c)
        p = os.path.join(W, f"evalset_{name}.jsonl")
        write_rows(rs, p)
        out[name] = p

    variant("high", lambda a, b: b)
    variant("g1zero", lambda a, b: 0 if a == 1 else a)
    # Derrick's own grades only
    cal = json.load(open(os.path.join(LAB, "derrick_inputs", "derrick-labels-2026-11-08.json")))["calibration"]
    dcal = collections.defaultdict(dict)
    for x in cal:
        dcal[x["query_id"]][x["code"]] = int(x["grade"])
    fr = {q["id"]: q for q in rows(os.path.join(LAB, "facet_real.jsonl"))}
    rs = json.loads(json.dumps(low))
    for q in rs:
        if q["id"] in fr:
            s = fr[q["id"]]
            q["relevant"] = dict(s["relevant"])
            q["judged_not_relevant"], q["judged_nonrelevant"], q["hard_negatives"] = [], s.get("judged_nonrelevant", []), []
        elif q["id"] in dcal:
            q["relevant"] = {c: g for c, g in dcal[q["id"]].items() if g > 0}
            q["judged_not_relevant"] = [c for c, g in dcal[q["id"]].items() if g == 0]
            q["judged_nonrelevant"], q["hard_negatives"] = [], []
        else:
            q["relevant"], q["judged_not_relevant"], q["judged_nonrelevant"], q["hard_negatives"] = {}, [], [], []
    p = os.path.join(W, "evalset_derrick.jsonl")
    write_rows(rs, p)
    out["derrick"] = p
    out["noai"] = os.path.join(DATA, "eval_work", "r8.8", "evalset_noai.jsonl")
    return out, this


# ---------------- scoring ----------------
def score(label_path, split, gains, stems=(BASE, *ARMS)):
    sc.GAINS = gains
    L = sc.load_labels(label_path, split)
    R = sc.Runs(RUNDIR, L)
    res = {}
    for s in stems:
        reps = []
        for r, raw in zip(R.reps(s), [R.raw[os.path.join(RUNDIR, f"{s}_r{k}.json")] for k in sc.REPEATS]):
            for q, m in r.items():
                ranked, rel = raw[q], L[q]["rel"]
                m["good5"] = float(any(rel.get(c, 0) >= 2 for c in ranked[:5]))
            reps.append(r)
        res[s] = reps
    return res, L


def qmean(reps, q, m):
    return float(np.mean([r[q][m] for r in reps]))


def mde(sd, n):
    if n < 2:
        return None
    return round(float((stats.t.ppf(0.975, n - 1) + stats.t.ppf(0.80, n - 1)) * sd / np.sqrt(n)), 4)


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: 2.0 if ps[i] is None else ps[i])
    adj, run = [None] * len(ps), 0.0
    for rank, i in enumerate(order):
        if ps[i] is None:
            continue
        run = max(run, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = round(run, 4)
    return adj


def delta(R, arm, qs, m, base=BASE):
    d = np.array([qmean(R[arm], q, m) - qmean(R[base], q, m) for q in qs])
    n = len(d)
    if n == 0:
        return {"n": 0}
    sd = float(d.std(ddof=1)) if n > 1 else 0.0
    if n > 1 and sd > 0:
        p = float(stats.ttest_1samp(d, 0.0, alternative="greater").pvalue)
    elif n > 1:
        p = 0.0 if d.mean() > 0 else 1.0
    else:
        p = None
    return {"n": n, "delta": round(float(d.mean()), 4), "ci95": sc.boot(d) if n > 1 else None,
            "wins": int((d > 0.005).sum()), "losses": int((d < -0.005).sum()), "ties": int((abs(d) <= 0.005).sum()),
            "sd_d": round(sd, 4), "mde80": mde(sd, n), "p_one_sided": None if p is None else round(p, 4),
            "per_repeat": [round(float(np.mean([R[arm][k][q][m] - R[base][k][q][m] for q in qs])), 4)
                           for k in range(3)]}


def family(R, qs, m, arms=ARMS):
    out = {a: delta(R, a, qs, m) for a in arms}
    for a, h in zip(arms, holm([out[a].get("p_one_sided") for a in arms])):
        out[a]["p_holm"] = h
    return out


def level(R, qs, m):
    return {s: {"mean": round(float(np.mean([qmean(R[s], q, m) for q in qs])), 4),
                "ci95": sc.boot([qmean(R[s], q, m) for q in qs], seed=0) if len(qs) > 1 else None}
            for s in R} if qs else {}


def gain_rule(d, extra_cost):
    """BRIEF.md: delta >= 0.03 with CI above 0, or >= 0.02 with more wins than losses and no extra cost."""
    if not d.get("n"):
        return False
    c1 = d["delta"] >= 0.03 and d["ci95"][0] > 0
    c2 = d["delta"] >= 0.02 and d["wins"] > d["losses"] and not extra_cost
    return bool(c1 or c2)


def ni(d):
    return bool(d["delta"] >= -0.005 and d["ci95"][0] >= -0.03)


# ---------------- tags and subsets ----------------
def meta_ps(stem):
    return [json.load(open(os.path.join(RUNDIR, f"{stem}_r{k}.json")))["meta"].get("per_search", {}) for k in (1, 2, 3)]


def main():
    variants, this = build_variants()
    ft = json.load(open(os.path.join(DATA, "evals", "facet_tags.json")))["tags"]
    tt = json.load(open(os.path.join(DATA, "evals", "trap_tags.json")))["tags"]
    ev = json.load(open(os.path.join(DATA, "eval_work", "r9_audit", "tags.json")))
    pk = json.load(open(os.path.join(DATA, "eval_work", "r9_media", "pilot_key.json")))
    labs = {q["id"]: q for q in rows(os.path.join(LAB, "evalset.jsonl"))}
    # Q8 paths from the base run files
    q8path = {}
    for f in ("runs/r8.5/q8_r1.json", "runs/r9/q8_facet_dev_r1.json"):
        for q, v in json.load(open(os.path.join(DATA, f)))["meta"]["per_search"].items():
            q8path[q] = v.get("path")
    a1ps, a2ps, m2ps = meta_ps("a1"), meta_ps("a2"), meta_ps("m2")
    a1_rewrite = {q for q, v in a1ps[0].items() if v.get("path") == "rewrite"}
    a1_named = {q for ps in a1ps for q, v in ps.items() if (v.get("frame") or {}).get("creator") == "named"}
    a2_fired = {q for q, v in a2ps[0].items() if v.get("intent_words")}

    report = {"round": "r9.1", "labels": "c4-r9.1 (evalset.jsonl after the r9.1 merge)", "arms": ARMS, "base": BASE,
              "sets": {}, "facets": {}, "traps": {}, "subsets": {}, "sensitivity": {}, "media": {}}
    detail = {}

    # ---- topic sets: dev, facet_dev
    for split in ("dev", "facet_dev"):
        sres = {}
        for var in ("low", "pre", "high", "g1zero", "derrick", "noai"):
            if var == "noai" and split != "dev":
                continue
            for gains in ("lin4", "col3"):
                R, L = score(variants[var], split, gains)
                qs = sorted(set(R[BASE][0]) & set(R["a1"][0]))
                key = f"{var}:{gains}"
                block = {"n": len(qs), "levels": level(R, qs, "ndcg10"), "ndcg10": family(R, qs, "ndcg10")}
                if var == "low":
                    for m in ("mrr", "p10", "success5", "good5", "unjudged10", "r100"):
                        block[m] = family(R, qs, m)
                        block["levels_" + m] = level(R, qs, m)
                    if gains == "lin4":
                        detail[split] = {s: {q: round(qmean(R[s], q, "ndcg10"), 4) for q in qs} for s in R}
                        # scope
                        for scope in ("ig", "yt"):
                            sq = [q for q in qs if L[q]["scope"] == scope]
                            block["scope_" + scope] = {"n": len(sq), "ndcg10": family(R, sq, "ndcg10")}
                        # route subsets
                        for name, sub in (("a1_rewrite", a1_rewrite), ("a2_fired", a2_fired),
                                          ("q8_instant", {q for q in qs if q8path.get(q) == "instant"})):
                            sq = [q for q in qs if q in sub]
                            block["sub_" + name] = {"n": len(sq), "ndcg10": family(R, sq, "ndcg10")}
                        # facets
                        fac = collections.defaultdict(list)
                        for q in qs:
                            tags = (labs[q].get("facets") or []) if split == "facet_dev" else ft.get(q, {}).get("facets", [])
                            for t in tags:
                                fac[t].append(q)
                        report["facets"][split] = {t: {"n": len(v), "ndcg10": family(R, v, "ndcg10"),
                                                        "good5": family(R, v, "good5")}
                                                    for t, v in sorted(fac.items())}
                        if split == "facet_dev":
                            fac2 = collections.defaultdict(list)
                            for q in qs:
                                for t in ft.get(q, {}).get("facets", []):
                                    fac2[t].append(q)
                            report["facets"]["facet_dev_tagger"] = {t: {"n": len(v), "ndcg10": family(R, v, "ndcg10")}
                                                                     for t, v in sorted(fac2.items())}
                        tr = collections.defaultdict(list)
                        for q in qs:
                            for t in tt.get(q, []) or ["none"]:
                                tr[t].append(q)
                        report["traps"][split] = {t: {"n": len(v), "ndcg10": family(R, v, "ndcg10")}
                                                  for t, v in sorted(tr.items())}
                        # share of relevant top-10 items resting on this round's grades
                        share = {}
                        for s in R:
                            tot = new = 0
                            for k in range(3):
                                raw = json.load(open(os.path.join(RUNDIR, f"{s}_r{k + 1}.json")))["queries"]
                                for q in qs:
                                    for c in raw[q][:10]:
                                        if c in L[q]["rel"]:
                                            tot += 1
                                            new += (q, c) in this
                            share[s] = {"relevant_top10": tot, "from_r9.1": new,
                                        "share": round(new / tot, 4) if tot else None}
                        block["share_relevant_top10_from_r9.1"] = share
                sres[key] = block
        report["sets"][split] = sres

    # trap cells pooled over dev + facet_dev (lin4, low labels)
    Rd, _ = score(variants["low"], "dev", "lin4")
    Rf, _ = score(variants["low"], "facet_dev", "lin4")
    Rall = {s: [{**a, **b} for a, b in zip(Rd[s], Rf[s])] for s in Rd}
    tr = collections.defaultdict(list)
    for q in sorted(Rall[BASE][0]):
        for t in tt.get(q, []) or ["none"]:
            tr[t].append(q)
    report["traps"]["dev+facet_dev"] = {t: {"n": len(v), "ndcg10": family(Rall, v, "ndcg10")} for t, v in sorted(tr.items())}

    # ---- known-item sets
    for split in ("known_dev", "ig_known_dev"):
        R, L = score(variants["low"], split, "exp2")
        qs = sorted(set(R[BASE][0]) & set(R["a1"][0]))
        block = {"n": len(qs)}
        for m in ("mrr2", "s10_2", "mrr", "success10"):
            block[m] = family(R, qs, m)
            block["levels_" + m] = level(R, qs, m)
        detail[split] = {s: {q: round(qmean(R[s], q, "mrr2"), 4) for q in qs} for s in R}
        for name, sub in (("a1_rewrite", a1_rewrite), ("a1_frame_named_creator", a1_named), ("a2_fired", a2_fired),
                          ("q8_instant", {q for q in qs if q8path.get(q) == "instant"}),
                          ("q8_rewrite", {q for q in qs if q8path.get(q) == "rewrite"})):
            sq = [q for q in qs if q in sub]
            block["sub_" + name] = {"n": len(sq), "mrr2": family(R, sq, "mrr2"), "s10_2": family(R, sq, "s10_2")}
        if split == "known_dev":
            samp = ev["known_dev_s100"]
            fac, trp = collections.defaultdict(list), collections.defaultdict(list)
            for q in qs:
                if q in samp:
                    for t in samp[q].get("facets", []):
                        fac[t].append(q)
                    if samp[q].get("creator_mode"):
                        fac["creator_" + samp[q]["creator_mode"]].append(q)
                    for t in samp[q].get("traps", []) or ["none"]:
                        trp[t].append(q)
            report["facets"]["known_dev_s100"] = {t: {"n": len(v), "mrr2": family(R, v, "mrr2")}
                                                   for t, v in sorted(fac.items())}
            report["traps"]["known_dev_s100"] = {t: {"n": len(v), "mrr2": family(R, v, "mrr2")}
                                                  for t, v in sorted(trp.items())}
        report["sets"][split] = {"exp2": block}

    # ---- media: looks / sound / said searches whose (YouTube) targets were described
    media = {}
    srch = {q: v for q, v in pk["searches"].items() if v["targets"]}
    tgt_rank = {}
    for s in (BASE, "m", "m2"):
        tgt_rank[s] = []
        for k in (1, 2, 3):
            raw = json.load(open(os.path.join(RUNDIR, f"{s}_r{k}.json")))["queries"]
            d = {}
            for q, v in srch.items():
                if q in raw:
                    pos = [raw[q].index(c) for c in v["targets"] if c in raw[q]]
                    d[q] = {"tmrr": 1.0 / (min(pos) + 1) if pos else 0.0, "t10": float(bool(pos) and min(pos) < 10)}
            tgt_rank[s].append(d)
    for set_name, split, metric, gains in (("dev", "dev", "ndcg10", "lin4"), ("facet_dev", "facet_dev", "ndcg10", "lin4"),
                                           ("known_dev", "known_dev", "mrr2", "exp2")):
        R, L = score(variants["low"], split, gains, stems=(BASE, "m", "m2"))
        cell = {}
        for fct in ("looks", "sound", "said", "any"):
            qs = sorted(q for q, v in srch.items() if v["split"] == set_name and q in R[BASE][0]
                        and (fct == "any" or fct in v["facets"]))
            cell[fct] = {"n": len(qs), metric: family(R, qs, metric, arms=["m", "m2"]),
                         "target_mrr": family(tgt_rank, qs, "tmrr", arms=["m", "m2"]),
                         "target_top10": family(tgt_rank, qs, "t10", arms=["m", "m2"])}
        media[set_name] = cell
    allq = sorted(q for q in srch if q in tgt_rank[BASE][0])
    media["all_sets"] = {}
    for fct in ("looks", "sound", "said", "any"):
        qs = [q for q in allq if fct == "any" or fct in srch[q]["facets"]]
        media["all_sets"][fct] = {"n": len(qs), "target_mrr": family(tgt_rank, qs, "tmrr", arms=["m", "m2"]),
                                  "target_top10": family(tgt_rank, qs, "t10", arms=["m", "m2"])}
    media["n_searches_with_described_targets"] = collections.Counter(v["split"] for v in srch.values())
    report["media"] = media

    # ---- cost / latency from meta
    cost = {}
    for s in ("a1", "a2", "m", "m2"):
        cost[s] = {k: json.load(open(os.path.join(RUNDIR, f"{s}_r{k}.json")))["meta"]["per_split"] for k in (1, 2, 3)}
    base_cost = {}
    for k in (1, 2, 3):
        a = json.load(open(os.path.join(DATA, "runs", "r8.5", f"q8_r{k}.json")))["meta"]["per_split"]
        b = json.load(open(os.path.join(DATA, "runs", "r9", f"q8_facet_dev_r{k}.json")))["meta"]["per_split"]
        base_cost[k] = {**a, **b}
    report["cost_meta"] = {"arms": cost, "q8": base_cost}
    report["judges"] = json.load(open(os.path.join(W, "disagree_r9.1.json")))
    json.dump(report, open(OUT_JSON, "w"), indent=1, default=lambda o: dict(o))
    json.dump(detail, open(os.path.join(W, "detail.json"), "w"), indent=1)
    print("wrote", OUT_JSON)


if __name__ == "__main__":
    main()
