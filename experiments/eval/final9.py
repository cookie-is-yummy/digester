"""PROTOTYPE ONLY - EVALUATOR SIDE. Round-9 final held-out step (BRIEF-9 "Stop rule and final scoring").

Only an evaluator-side agent runs this file: it reads $DIGESTER_DATA/evals/labels/ and hidden query texts.
Aggregates go to --out (git, no texts / codes / per-search numbers); per-search numbers and tags stay under
$DIGESTER_DATA/eval_work/r9.F/ (gitignored).

subcommands:
  tag        evaluator-side facet / trap tags (Phase A tagger r9c-v2 from audit_r9.py: rules for every facet but
             creator, gpt-5.4-nano prompt r9t-v2 for creator, examples_of and shorthand) for known_test_clean and
             ig_known_test. facet_test and ig_real reuse the Phase A tags (tags.json, evaluator-side); facet_test
             facets are Derrick's own based_on ticks. Writes eval_work/r9.F/heldout_tags_EVALUATOR_ONLY.json.
  score      facet_test scoring 1 of 3: H0r8, Q8, FM (runs/r9/*_facet_test_r{1,2,3}).
             want=exact (3): target only, mrr2 / s10_2 (target grade 3 counts as >= 2); no pooling.
             want=like (12): target = 3 plus the r9.F pool (two judges, lower grade; higher = sensitivity);
             nDCG@10 lin4 (gains 0/1/2/3, primary) and col3 (3, 2 -> 2, gains 2^g - 1).
             Label variants: low (merged evalset), high, g1to0 (this round's grade 1 -> 0), seed (Derrick's
             target only, labels/facet_real.jsonl). Paired delta = per-search mean over the 3 repeats; 95% paired
             bootstrap; W/L/T at |d| > 0.005; MDE = (t.975 + t.80) * sd_d / sqrt(n); one-sided paired t-test;
             Holm over the 3 comparisons per slice and metric.
  breakdown  per facet and per trap, Q8 - H0r8 and FM - Q8 with MDE per cell, on known_test_clean and
             ig_known_test (runs/final8, mrr2 / s10_2), ig_real (runs/r9, nDCG@10 lin4 on the merged labels and
             target mrr2; with and without the one search quoted in BRIEF-9) and facet_test. No new scorings:
             the methods and the run files are the ones already scored.
  scorecard  Q8's held-out values per scorecard row (r9-scorecard.md definitions: hit10 / hit5 on exact
             searches, good5 on like searches, worked = hit10 | good5, Gate 1 = hit5 | good5) on facet_test,
             known_test_clean and ig_known_test, with CI, n and MDE (sd of Q8 - H0r8 on the same cell).

usage: final9.py tag | score --out OUT.json | breakdown --out OUT.json | scorecard --out OUT.json
"""
import argparse
import collections
import concurrent.futures as cf
import copy
import json
import math
import os
import re
import sys

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_r9 as au
import score_c4 as sc

DATA = sc.DATA
LAB = os.path.join(DATA, "evals", "labels")
W = os.path.join(DATA, "eval_work", "r9.F")
TAGS = os.path.join(W, "heldout_tags_EVALUATOR_ONLY.json")
METHODS = {"H0r8": "h0r8", "Q8": "q8", "FM": "fm"}
CMPS3 = [("Q8", "H0r8"), ("FM", "H0r8"), ("FM", "Q8")]
CMPS2 = [("Q8", "H0r8"), ("FM", "Q8")]
RUNSET = {"facet_test": ("r9", "facet_test"), "ig_real": ("r9", "ig_real"),
          "known_test_clean": ("final8", "known_test"), "ig_known_test": ("final8", "ig_known_test")}
FACETS = ["creator", "creator_named", "creator_described", "topic", "type", "looks", "sound", "said", "tone",
          "examples", "when", "platform"]
TRAPS = au.TRAPS + ["none"]
B = 2000


def jl(p):
    return [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]


def split_ids(name):
    if name == "known_test_clean":
        return sorted(json.load(open(os.path.join(LAB, "known_test_clean_ids.json")))["ids"])
    return sorted(json.load(open(os.path.join(DATA, "evals", "split.json")))[name])


def load_runs(name):
    d, stem = RUNSET[name]
    return {m: [json.load(open(os.path.join(DATA, "runs", d, f"{s}_{stem}_r{k}.json")))["queries"] for k in (1, 2, 3)]
            for m, s in METHODS.items()}


# ---------------------------------------------------------------- tags
def tag(args):
    texts = {}
    for name, fn in (("known_test_clean", "known_test_queries.jsonl"), ("ig_known_test", "ig_known_test_queries.jsonl")):
        ids = set(split_ids(name))
        texts[name] = {r["id"]: r["query"] for r in jl(os.path.join(LAB, fn)) if r["id"] in ids}
    cpath = os.path.join(W, "tag_cache_heldout.json")
    cache = json.load(open(cpath)) if os.path.exists(cpath) else {}
    todo = sorted({q for S in texts.values() for q in S.values() if q.strip()} - {k.split("|", 1)[1] for k in cache})
    print(f"llm tag calls: {len(todo)}", file=sys.stderr)
    with cf.ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(lambda q: au.llm_tag(q, cache), todo))
    json.dump(cache, open(cpath, "w"), ensure_ascii=False)
    out = {}
    for name, S in texts.items():
        out[name] = {}
        for sid, q in S.items():
            r, m = au.rule_tags(q), cache["r9t-v2|" + q]
            c = au.combine(r, m)
            traps = au.rule_traps(q) | (set(m["traps"]) - {"format_as_topic"})
            if c["creator_mode"] == "described":
                traps.add("described_creator")
            else:
                traps.discard("described_creator")
            out[name][sid] = {**c, "traps": sorted(traps, key=au.TRAPS.index)}
    p9 = json.load(open(os.path.join(DATA, "eval_work", "r9_audit", "tags.json")))
    ev = {r["id"]: r for r in jl(os.path.join(LAB, "evalset.jsonl"))}
    for name in ("ig_real", "facet_test"):
        out[name] = {}
        for sid, t in p9[name].items():
            f = list(t["facets"])
            src = "tagger r9c-v2"
            if name == "facet_test":  # Derrick's own ticks are ground truth; creator mode from the tagger
                f, src = list(ev[sid].get("facets") or []), "derrick based_on"
            out[name][sid] = {"facets": f, "creator_mode": t.get("creator_mode"), "specificity": t["specificity"],
                              "traps": t["traps"], "facet_source": src}
    json.dump(out, open(TAGS, "w"), indent=1, ensure_ascii=False)
    for name, S in out.items():
        cnt = collections.Counter(f for v in S.values() for f in v["facets"])
        tc = collections.Counter(t for v in S.values() for t in v["traps"])
        print(name, len(S), dict(cnt), dict(tc))


def cell_groups(tags, ids):
    """{group: [ids]} per facet (creator split named / described) and per trap ('none' = no trap)."""
    fac, trp = collections.defaultdict(list), collections.defaultdict(list)
    for q in ids:
        t = tags[q]
        fs = set(t["facets"])
        if "creator" in fs:
            fs.add("creator_described" if t.get("creator_mode") == "described" else "creator_named")
        for f in fs:
            fac[f].append(q)
        for x in t["traps"] or ["none"]:
            trp[x].append(q)
    return ({f: fac[f] for f in FACETS if f in fac}, {x: trp[x] for x in TRAPS if x in trp})


# ---------------------------------------------------------------- labels and per-search metrics
def to_lab(r):
    rel = {c: int(g) for c, g in r["relevant"].items() if g > 0}
    judged = (set(r["relevant"]) | set(r.get("judged_not_relevant", [])) | set(r.get("judged_nonrelevant", []))
              | set(r.get("hard_negatives", [])))
    return {"rel": rel, "judged": judged, "kinds": r["kinds"], "scope": r["scope"]}


def ndcg(ranked, rel, gains):
    def g(x):
        if gains == "lin4":
            return float(x)
        return 2.0 ** min(x, 2) - 1 if gains == "col3" else 2.0 ** x - 1
    dcg = sum(g(rel.get(c, 0)) / math.log2(i + 2) for i, c in enumerate(ranked[:10]))
    ideal = sorted(rel.values(), reverse=True)[:10]
    idcg = sum(g(x) / math.log2(i + 2) for i, x in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def per_search(ranked, lab, target, plat):
    rel = lab["rel"]
    pos = {}
    for i, c in enumerate(ranked):
        pos.setdefault(c, i)
    ft = min((pos[c] for c in target if c in pos), default=None)
    top = ranked[:10]
    return {"ndcg_lin4": ndcg(ranked, rel, "lin4"), "ndcg_col3": ndcg(ranked, rel, "col3"),
            "tmrr": 1.0 / (ft + 1) if ft is not None else 0.0,
            "hit10": float(ft is not None and ft < 10), "hit5": float(ft is not None and ft < 5),
            "good5": float(any(rel.get(c, 0) >= 2 for c in ranked[:5])),
            "exact5": float(any(rel.get(c, 0) >= 3 for c in ranked[:5])),
            "p10": sum(1 for c in top if c in rel) / 10,
            "good_p10": sum(1 for c in top if rel.get(c, 0) >= 2) / 10,
            "success5": float(any(c in rel for c in ranked[:5])),
            "unjudged10": sum(1 for c in top if c not in lab["judged"] and c in plat) / 10}


def compute(runs, L, targets, plat):
    """{method: {q: {metric: mean over repeats}}}."""
    out = {}
    for m, reps in runs.items():
        out[m] = {}
        for q in L:
            per = [per_search(r[q], L[q], targets[q], plat) for r in reps]
            out[m][q] = {k: float(np.mean([p[k] for p in per])) for k in per[0]}
            out[m][q]["_reps"] = {k: [p[k] for p in per] for k in ("ndcg_lin4", "tmrr", "hit10")}
    return out


# ---------------------------------------------------------------- statistics
def mde(sd, n):
    if n < 2 or sd == 0:
        return None
    return round(float((stats.t.ppf(0.975, n - 1) + stats.t.ppf(0.80, n - 1)) * sd / np.sqrt(n)), 3)


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: 2.0 if ps[i] is None else ps[i])
    adj, run = [None] * len(ps), 0.0
    for rank, i in enumerate(order):
        if ps[i] is None:
            continue
        run = max(run, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = run
    return adj


def level(V, m, qs, met):
    v = [V[m][q][met] for q in qs]
    return {"mean": round(float(np.mean(v)), 3), "ci95": sc.boot(v, seed=0) if len(v) > 1 else None}


def delta(V, a, b, qs, met):
    d = np.array([V[a][q][met] - V[b][q][met] for q in qs])
    n = len(d)
    sd = float(d.std(ddof=1)) if n > 1 else 0.0
    if n > 1 and sd > 0:
        p = float(stats.ttest_1samp(d, 0.0, alternative="greater").pvalue)
    elif n > 1:
        p = 0.0 if d.mean() > 0 else 1.0
    else:
        p = None
    md = mde(sd, n)
    return {"n": n, "delta": round(float(d.mean()), 4) if n else None, "ci95": sc.boot(d) if n > 1 else None,
            "wins": int((d > 0.005).sum()), "losses": int((d < -0.005).sum()), "ties": int((abs(d) <= 0.005).sum()),
            "sd_d": round(sd, 3), "mde80": md, "p_one_sided": None if p is None else round(p, 4),
            "within_noise": bool(md is None or abs(float(d.mean())) < md)}


def block(V, qs, metrics, cmps=CMPS3):
    res = {"n": len(qs), "levels": {}, "comparisons": {}}
    if len(qs) < 1:
        return res
    for m in METHODS:
        res["levels"][m] = {met: level(V, m, qs, met) for met in metrics}
    for met in metrics:
        rows = [delta(V, a, b, qs, met) for a, b in cmps]
        for (a, b), row, h in zip(cmps, rows, holm([r["p_one_sided"] for r in rows])):
            row["p_holm"] = None if h is None else round(h, 4)
            res["comparisons"].setdefault(f"{a}-{b}", {})[met] = row
    return res


def per_rep_delta(V, a, b, qs, met):
    return [round(float(np.mean([V[a][q]["_reps"][met][k] - V[b][q]["_reps"][met][k] for q in qs])), 4)
            for k in range(3)]


# ---------------------------------------------------------------- facet_test scoring
def ft_labels():
    ids = split_ids("facet_test")
    ev = {r["id"]: r for r in jl(os.path.join(LAB, "evalset.jsonl")) if r["id"] in ids}
    seed = {r["id"]: r for r in jl(os.path.join(LAB, "facet_real.jsonl")) if r["id"] in ids}
    sheet = jl(os.path.join(W, "sheet_r9.F.jsonl"))
    high = json.load(open(os.path.join(W, "grades_r9.F_high.json")))
    this_round = {(r["query_id"], r["code"]) for r in sheet}
    low = {q: to_lab(r) for q, r in ev.items()}
    hi = copy.deepcopy(low)
    for r, g in zip(sheet, high):
        if g > 0:
            hi[r["query_id"]]["rel"][r["code"]] = int(g)
        else:
            hi[r["query_id"]]["rel"].pop(r["code"], None)
    g10 = copy.deepcopy(low)
    for q, c in this_round:
        if g10[q]["rel"].get(c) == 1:
            del g10[q]["rel"][c]
    sd = {q: to_lab(r) for q, r in seed.items()}
    targets = {q: {c for c, g in sd[q]["rel"].items() if g >= 2} for q in ids}
    return ids, ev, {"low": low, "high": hi, "g1to0": g10, "seed": sd}, targets, this_round


def score(args):
    plat = sc.platforms()
    ids, ev, VAR, targets, this_round = ft_labels()
    runs = load_runs("facet_test")
    spec = {q: ev[q]["specificity"] for q in ids}
    sl = {"exact": [q for q in ids if spec[q] == "exact"], "like": [q for q in ids if spec[q] == "like"], "all": ids,
          "ig": [q for q in ids if ev[q]["scope"] == "ig"], "yt": [q for q in ids if ev[q]["scope"] == "yt"]}
    sl["like_ig"] = [q for q in sl["like"] if ev[q]["scope"] == "ig"]
    sl["like_yt"] = [q for q in sl["like"] if ev[q]["scope"] == "yt"]
    V = {var: compute(runs, L, targets, plat) for var, L in VAR.items()}
    rep = {"split": "facet_test", "scoring": "1 of 3", "round": "r9.F", "label_round": "c4-r9.F",
           "methods": {m: f"runs/r9/{s}_facet_test_r{{1,2,3}}" for m, s in METHODS.items()},
           "slices_n": {k: len(v) for k, v in sl.items()}}
    # exact slice: target only
    rep["exact_target"] = block(V["seed"], sl["exact"], ["tmrr", "hit10", "hit5"])
    rep["target_only"] = {s: block(V["seed"], sl[s], ["tmrr", "hit10", "hit5"]) for s in ("like", "all")}
    # like slice: pooled
    pm = ["ndcg_lin4", "ndcg_col3", "good5", "exact5", "success5", "p10", "good_p10", "unjudged10"]
    rep["like_pooled"] = block(V["low"], sl["like"], pm)
    rep["like_pooled"]["per_repeat_delta_lin4"] = {f"{a}-{b}": per_rep_delta(V["low"], a, b, sl["like"], "ndcg_lin4")
                                                   for a, b in CMPS3}
    rep["like_by_scope"] = {s: block(V["low"], sl[s], ["ndcg_lin4", "good5"]) for s in ("like_ig", "like_yt")}
    rep["all_pooled_lin4"] = block(V["low"], sl["all"], ["ndcg_lin4"])
    rep["sensitivity"] = {var: block(V[var], sl["like"], ["ndcg_lin4", "ndcg_col3", "good5"])
                          for var in ("high", "g1to0", "seed")}
    # pooled share
    tot = new = 0
    for m, reps in runs.items():
        for r in reps:
            for q in sl["like"]:
                for c in r[q][:10]:
                    if VAR["low"][q]["rel"].get(c, 0) > 0:
                        tot += 1
                        new += (q, c) in this_round
    rep["relevant_top10_share_from_r9F_grades"] = round(new / tot, 3) if tot else None
    sign_same = sum(np.sign(round(V["low"]["Q8"][q]["ndcg_lin4"] - V["low"]["H0r8"][q]["ndcg_lin4"], 3))
                    == np.sign(round(V["high"]["Q8"][q]["ndcg_lin4"] - V["high"]["H0r8"][q]["ndcg_lin4"], 3))
                    for q in sl["like"])
    rep["q8_h0r8_sign_same_low_vs_high"] = round(sign_same / len(sl["like"]), 3)
    g = [VAR["low"][q]["rel"].get(c, 0) for (q, c) in this_round]
    gh = [VAR["high"][q]["rel"].get(c, 0) for (q, c) in this_round]
    rep["pooled_grades"] = {"items": len(this_round), "searches": len({q for q, _ in this_round}),
                            "dist4_lower_rule": {str(x): g.count(x) for x in range(4)},
                            "dist4_higher_rule": {str(x): gh.count(x) for x in range(4)}}
    dis = json.load(open(os.path.join(W, "disagree_r9.F.json")))
    rep["judge_disagreement"] = {k: dis[k] for k in ("exact4", "steps", "kappa4", "kappa4_linear", "mean4",
                                                     "per_platform")}
    rep["judge_disagreement"]["kappa_rel"] = dis["A_vs_B_3pt"]["kappa_rel"]
    rep["judge_disagreement"]["kappa_rel_ci"] = dis["A_vs_B_3pt"]["kappa_rel_ci"]
    rep["judge_disagreement"]["disagree_rel"] = round(float(np.mean(
        [(a >= 1) != (b >= 1) for a, b in _pairs()])), 3)
    rep["judge_disagreement"]["disagree_good"] = round(float(np.mean(
        [(a >= 2) != (b >= 2) for a, b in _pairs()])), 3)
    # cost / latency
    rep["cost_latency"] = {}
    for m, s in METHODS.items():
        rows = [json.load(open(os.path.join(DATA, "runs", "r9", f"{s}_facet_test_r{k}.json")))["meta"]
                for k in (1, 2, 3)]
        ps = [r["per_split"]["facet_test"] for r in rows]
        rep["cost_latency"][m] = {
            "cost_per_1k_searches_usd": [p["cost_per_1k_searches_usd"] for p in ps],
            "total_p50_s": [p["total_p50_s"] for p in ps], "total_p95_s": [p["total_p95_s"] for p in ps],
            "paths": {k.split(":", 1)[1]: v for k, v in rows[0].get("counts", {}).items()
                      if k.split(":", 1)[1] in ("instant", "rewrite", "refined_rewrite")}}
    # per facet (Derrick's ticks) and per trap (tagger), facet_test
    tags = json.load(open(TAGS))["facet_test"]
    fac, trp = cell_groups(tags, ids)
    rep["per_facet"] = {f: cell(V["low"], qs, ["ndcg_lin4", "tmrr"]) for f, qs in fac.items()}
    rep["per_trap"] = {t: cell(V["low"], qs, ["ndcg_lin4", "tmrr"]) for t, qs in trp.items()}
    json.dump(rep, open(args.out, "w"), indent=1)
    json.dump({var: {m: {q: {k: round(v, 4) for k, v in d.items() if k != "_reps"} for q, d in V[var][m].items()}
                     for m in METHODS} for var in V}, open(os.path.join(W, "facet_test_detail.json"), "w"), indent=1)
    show(rep)


def _pairs():
    import judges9
    sheet = judges9.read_sheet(os.path.join(W, "sheet_r9.F.jsonl"))
    return [(g["A"], g["B"]) for g in judges9.grades_of(sheet, "j9-v1")]


def cell(V, qs, metrics):
    if len(qs) < 3:
        return {"n": len(qs), "suppressed": "n < 3"}
    out = {"n": len(qs)}
    for met in metrics:
        out[met] = {"Q8": level(V, "Q8", qs, met), "H0r8": round(float(np.mean([V["H0r8"][q][met] for q in qs])), 3),
                    "FM": round(float(np.mean([V["FM"][q][met] for q in qs])), 3)}
        for a, b in CMPS2:
            out[met][f"{a}-{b}"] = delta(V, a, b, qs, met)
    return out


def show(rep):
    def fmt(c, met, key):
        x = c["comparisons"][key][met]
        return f"{key} {x['delta']:+.3f} {x['ci95']} {x['wins']}/{x['losses']}/{x['ties']} mde {x['mde80']} holm {x['p_holm']}"
    for name in ("exact_target", "like_pooled"):
        c = rep[name]
        mets = list(next(iter(c["levels"].values())))
        for met in mets[:3]:
            lv = " ".join(f"{m} {c['levels'][m][met]['mean']:.3f}" for m in METHODS)
            print(f"{name} n{c['n']} {met}: {lv} | " + " | ".join(fmt(c, met, f"{a}-{b}") for a, b in CMPS3))


# ---------------------------------------------------------------- breakdowns
def quoted_ig_real():
    """The ig_real search whose text appears verbatim in BRIEF-9 (r9-ig-real verifier note). Returns its id only."""
    brief = " ".join(open(os.path.join(os.path.dirname(HERE), "BRIEF-9.md"), encoding="utf-8").read().lower().split())
    hits = [r["id"] for r in jl(os.path.join(LAB, "ig_real_queries.jsonl"))
            if r["query"].strip() and re.search(r"\b" + re.escape(" ".join(r["query"].lower().split())) + r"\b", brief)]
    return hits


def set_values(name, plat):
    ids = split_ids(name)
    ev = {r["id"]: r for r in jl(os.path.join(LAB, "evalset.jsonl")) if r["id"] in set(ids)}
    L = {q: to_lab(ev[q]) for q in ids}
    if name in ("ig_real", "facet_test"):
        seedf = "ig_real.jsonl" if name == "ig_real" else "facet_real.jsonl"
        seed = {r["id"]: r for r in jl(os.path.join(LAB, seedf))}
        targets = {q: {c for c, g in seed[q]["relevant"].items() if g >= 2} for q in ids}
    else:
        targets = {q: {c for c, g in L[q]["rel"].items() if g >= 2} for q in ids}
    return ids, ev, compute(load_runs(name), L, targets, plat)


def breakdown(args):
    plat = sc.platforms()
    tags = json.load(open(TAGS))
    rep = {"note": "No new scorings: same methods and run files as the scorings already made "
                   "(known_test_clean / ig_known_test scoring 1 = r8-final; ig_real scoring 1 = r9-ig-real; "
                   "facet_test scoring 1 = this step).", "sets": {}}
    quoted = quoted_ig_real()
    rep["ig_real_quoted_search_found"] = len(quoted)
    for name in ("known_test_clean", "ig_known_test", "ig_real", "facet_test"):
        ids, ev, V = set_values(name, plat)
        mets = ["tmrr", "hit10"] if name in ("known_test_clean", "ig_known_test") else ["ndcg_lin4", "tmrr"]
        variants = {name: ids}
        if name == "ig_real":
            variants["ig_real_excl_quoted"] = [q for q in ids if q not in quoted]
        for vname, vids in variants.items():
            fac, trp = cell_groups(tags[name], vids)
            out = {"n": len(vids), "metrics": mets, "facet_source": next(iter(tags[name].values())).get(
                "facet_source", "tagger r9c-v2"), "all": cell(V, vids, mets),
                "per_facet": {f: cell(V, qs, mets) for f, qs in fac.items()},
                "per_trap": {t: cell(V, qs, mets) for t, qs in trp.items()},
                "facet_mix": {f: len(qs) for f, qs in fac.items()}, "trap_mix": {t: len(qs) for t, qs in trp.items()}}
            if name == "ig_real":
                kind = {q: ev[q].get("search_kind") for q in vids}
                tm = [q for q in vids if kind[q] in ("topic", "meta")]
                ki = [q for q in vids if kind[q] == "known_item"]
                out["slices"] = {"topic+meta_ndcg_lin4": block(V, tm, ["ndcg_lin4", "good5"]),
                                 "known_item_tmrr": block(V, ki, ["tmrr", "hit10"]),
                                 "all_target_tmrr": block(V, vids, ["tmrr"])}
            rep["sets"][vname] = out
            print(vname, len(vids), {f: c.get("n") for f, c in out["per_facet"].items()})
    json.dump(rep, open(args.out, "w"), indent=1)


# ---------------------------------------------------------------- scorecard column
def scorecard(args):
    plat = sc.platforms()
    tags = json.load(open(TAGS))
    rng = np.random.default_rng(9)
    rep = {"definitions": "r9-scorecard.md: hit10 / hit5 = target in top 10 / 5 (exact searches); good5 = a "
                          "grade >= 2 item in the top 5 (like searches, merged labels incl. r9.F pooled AI grades); "
                          "good5_floor = Derrick's own grades only (his target); worked = hit10 | good5; "
                          "gate = hit5 | good5.", "sets": {}}
    for name in ("facet_test", "known_test_clean", "ig_known_test"):
        ids, ev, V = set_values(name, plat)
        spec = {q: (ev[q].get("specificity") if name == "facet_test" else "exact") for q in ids}

        def val(m, q, met):
            x = V[m][q]
            ex = spec[q] == "exact"
            if met == "sat":
                return x["hit10"] if ex else x["good5"]
            if met == "gate":
                return x["hit5"] if ex else x["good5"]
            if met == "good5_floor":
                return x["hit5"]  # Derrick's only grade on facet_test is the target
            if met == "tgt10":
                return x["hit10"]
            return x[met]
        fac, _ = cell_groups(tags[name], ids)
        groups = {"all": ids, "exact": [q for q in ids if spec[q] == "exact"],
                  "like": [q for q in ids if spec[q] == "like"],
                  "ig": [q for q in ids if ev[q]["scope"] == "ig"], "yt": [q for q in ids if ev[q]["scope"] == "yt"],
                  **fac}
        out = {}
        for g, gq in groups.items():
            c = {"n": len(gq), "n_exact": sum(spec[q] == "exact" for q in gq), "n_like": sum(spec[q] == "like" for q in gq)}
            if len(gq) < 3:
                out[g] = {**c, "suppressed": "n < 3"}
                continue
            mlist = ["sat", "gate"] + (["hit10", "hit5"] if c["n_exact"] >= 3 else []) \
                + (["good5", "good5_floor", "tgt10"] if c["n_like"] >= 3 else [])
            for met in mlist:
                sub = gq if met in ("sat", "gate") else [q for q in gq if spec[q] == ("exact" if met in ("hit10", "hit5") else "like")]
                v8 = np.array([val("Q8", q, met) for q in sub])
                v0 = np.array([val("H0r8", q, met) for q in sub])
                vf = np.array([val("FM", q, met) for q in sub])
                bs = v8[rng.integers(0, len(sub), (B, len(sub)))].mean(axis=1)
                sd = float((v8 - v0).std(ddof=1)) if len(sub) > 1 else 0.0
                c[met] = {"n": len(sub), "q8": round(float(v8.mean()), 3),
                          "ci95": [round(float(np.percentile(bs, 2.5)), 3), round(float(np.percentile(bs, 97.5)), 3)],
                          "h0r8": round(float(v0.mean()), 3), "fm": round(float(vf.mean()), 3),
                          "d_vs_h0r8": round(float((v8 - v0).mean()), 3), "sd_d": round(sd, 3), "mde": mde(sd, len(sub))}
            out[g] = c
        rep["sets"][name] = out
        for g, c in out.items():
            print(name, g, c["n"], {k: (v["q8"], v["ci95"], v["mde"]) for k, v in c.items() if isinstance(v, dict)})
    json.dump(rep, open(args.out, "w"), indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["tag", "score", "breakdown", "scorecard"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    os.makedirs(W, exist_ok=True)
    {"tag": tag, "score": score, "breakdown": breakdown, "scorecard": scorecard}[a.cmd](a)


if __name__ == "__main__":
    main()
