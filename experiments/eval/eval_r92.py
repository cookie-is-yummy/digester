"""PROTOTYPE ONLY - EVALUATOR SIDE. Round 9.2 evaluation (BRIEF-9 Track 1 item 2: B1 named-creator lookup, B2 soft
time window, B3 additive intent frame) vs Q8.

Reads $DIGESTER_DATA/evals/labels/ (evaluator only). Writes aggregates to experiments/results/r9.2-eval.json and
per-search detail to $DIGESTER_DATA/eval_work/r9.2/ (gitignored). No paid calls.

Runs: eval_work/r9.2/runs/{q8,b1,b2,b3}_r{1,2,3}.json; q8 = runs/r9.1/q8ref_r{k} (the experimenter reproduced it
602/602, 1,000 deep, from caches), arms = runs/r9.2/*. yt_holdout is in the files and never scored.
Label variants (dev, facet_dev): pre (before r9.2 pooling = c4-r9.1), low (primary: two-judge lower grade, merged),
high (this round's items at the higher grade), g1zero (this round's 4-point grade-1 items -> 0), derrick (Derrick's
own grades only), noai (dev: r8.8's no-AI-grade file). Gains lin4 (0/1/2/3) and col3 (3,2 -> 2) on topic sets;
known-item sets use mrr2 / s10_2 (gain-free).
Stats as eval_r91: paired per-search delta = mean over 3 repeats; 95% bootstrap CI (score_c4.boot); W/L/T at
|d| > 0.005; MDE = (t.975 + t.80) sd_d / sqrt(n); one-sided paired t p; Holm over the 3 arms per set x metric.
"""
import collections
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import eval_r91 as e91  # noqa: E402
import score_c4 as sc  # noqa: E402

DATA = sc.DATA
LAB = os.path.join(DATA, "evals", "labels")
W = os.path.join(DATA, "eval_work", "r9.2")
RUNDIR = os.path.join(W, "runs")
ARMS = ["b1", "b2", "b3"]
BASE = "q8"
OUT_JSON = os.path.join(os.path.dirname(HERE), "results", "r9.2-eval.json")
EXTRA_COST = {"b1": False, "b2": False, "b3": True}

rows, write_rows, collapse, qmean, mde, holm = e91.rows, e91.write_rows, e91.collapse, e91.qmean, e91.mde, e91.holm
gain_rule, ni = e91.gain_rule, e91.ni


def build_variants():
    sheet = rows(os.path.join(W, "sheet_r9.2.jsonl"))
    lo = json.load(open(os.path.join(W, "grades_r9.2_low.json")))
    hi = json.load(open(os.path.join(W, "grades_r9.2_high.json")))
    this = {(r["query_id"], r["code"]): (int(a), int(b)) for r, a, b in zip(sheet, lo, hi)}
    low = rows(os.path.join(LAB, "evalset.jsonl"))
    out = {"pre": os.path.join(LAB, "evalset.pre_r9.2.jsonl"), "low": os.path.join(LAB, "evalset.jsonl")}

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
    out["derrick"] = os.path.join(DATA, "eval_work", "r9.1", "evalset_derrick.jsonl")  # Derrick-only rows, unchanged
    out["noai"] = os.path.join(DATA, "eval_work", "r8.8", "evalset_noai.jsonl")
    return out, this


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


def delta(R, arm, qs, m, base=BASE):
    return e91.delta(R, arm, qs, m, base)


def family(R, qs, m, arms=ARMS):
    out = {a: delta(R, a, qs, m) for a in arms}
    for a, h in zip(arms, holm([out[a].get("p_one_sided") for a in arms])):
        out[a]["p_holm"] = h
    return out


def level(R, qs, m):
    return e91.level(R, qs, m)


def raw(stem, k):
    return json.load(open(os.path.join(RUNDIR, f"{stem}_r{k}.json")))


def main():
    variants, this = build_variants()
    ft = json.load(open(os.path.join(DATA, "evals", "facet_tags.json")))["tags"]
    tt = json.load(open(os.path.join(DATA, "evals", "trap_tags.json")))["tags"]
    ev = json.load(open(os.path.join(DATA, "eval_work", "r9_audit", "tags.json")))
    labs = {q["id"]: q for q in rows(os.path.join(LAB, "evalset.jsonl"))}
    runs = {s: [raw(s, k) for k in (1, 2, 3)] for s in (BASE, *ARMS)}
    q8path = {q: v.get("path") for q, v in runs[BASE][0]["meta"]["per_search"].items()}
    fired = {
        "b1": {q for d in runs["b1"] for q, v in d["meta"]["per_search"].items() if (v.get("b1") or {}).get("fired")},
        "b2": {q for d in runs["b2"] for q, v in d["meta"]["per_search"].items() if (v.get("b2") or {}).get("fired")},
        "b3": {q for d in runs["b3"] for q, v in d["meta"]["per_search"].items() if (v.get("frame") or {}).get("used")},
    }
    # top-10 changed in any repeat (label-free)
    t10 = {a: {q for k in range(3) for q in runs[a][k]["queries"]
               if runs[a][k]["queries"][q][:10] != runs[BASE][k]["queries"][q][:10]} for a in ARMS}
    # sanity: unfired searches identical to Q8, 1,000 deep, every repeat
    unfired_identical = {}
    for a in ("b1", "b2"):
        bad = sum(1 for k in range(3) for q in runs[a][k]["queries"]
                  if q not in fired[a] and runs[a][k]["queries"][q][:1000] != runs[BASE][k]["queries"][q][:1000])
        unfired_identical[a] = bad == 0

    report = {"round": "r9.2", "labels": "c4-r9.2 (evalset.jsonl after the r9.2 merge)", "arms": ARMS, "base": BASE,
              "base_files": "runs/r9.1/q8ref_r{1,2,3}", "unfired_identical_to_q8": unfired_identical,
              "fired_counts": {}, "sets": {}, "facets": {}, "traps": {}, "sensitivity": {}}
    splits_all = ("dev", "facet_dev", "known_dev", "ig_known_dev")
    sp = json.load(open(os.path.join(DATA, "evals", "split.json")))
    for a in ARMS:
        report["fired_counts"][a] = {s: {"fired": len(fired[a] & set(sp[s])), "top10_changed_any_repeat":
                                         len(t10[a] & set(sp[s]))} for s in splits_all}
    detail = {}

    for split in ("dev", "facet_dev"):
        sres = {}
        for var in ("low", "pre", "high", "g1zero", "derrick", "noai"):
            if var == "noai" and split != "dev":
                continue
            for gains in ("lin4", "col3"):
                R, L = score(variants[var], split, gains)
                qs = sorted(set(R[BASE][0]) & set(R["b1"][0]))
                key = f"{var}:{gains}"
                block = {"n": len(qs), "levels": level(R, qs, "ndcg10"), "ndcg10": family(R, qs, "ndcg10")}
                for a in ("b1", "b2", "b3"):
                    sq = [q for q in qs if q in fired[a]]
                    block["fired_" + a] = {"n": len(sq), "ndcg10": family(R, sq, "ndcg10", arms=[a])[a]}
                if var == "low":
                    for m in ("mrr", "p10", "success5", "good5", "unjudged10", "r100"):
                        block[m] = family(R, qs, m)
                        block["levels_" + m] = level(R, qs, m)
                    if gains == "lin4":
                        detail[split] = {s: {q: round(qmean(R[s], q, "ndcg10"), 4) for q in qs} for s in R}
                        for scope in ("ig", "yt"):
                            sq = [q for q in qs if L[q]["scope"] == scope]
                            block["scope_" + scope] = {"n": len(sq), "ndcg10": family(R, sq, "ndcg10")}
                        sq = [q for q in qs if q in t10["b3"]]
                        block["b3_top10_changed"] = {"n": len(sq), "ndcg10": family(R, sq, "ndcg10", arms=["b3"])["b3"]}
                        fac = collections.defaultdict(list)
                        for q in qs:
                            tags = (labs[q].get("facets") or []) if split == "facet_dev" else ft.get(q, {}).get("facets", [])
                            for t in tags:
                                fac[t].append(q)
                        report["facets"][split] = {t: {"n": len(v), "ndcg10": family(R, v, "ndcg10"),
                                                        "fired": {a: len(set(v) & fired[a]) for a in ARMS}}
                                                    for t, v in sorted(fac.items())}
                        tr = collections.defaultdict(list)
                        for q in qs:
                            for t in tt.get(q, []) or ["none"]:
                                tr[t].append(q)
                        report["traps"][split] = {t: {"n": len(v), "ndcg10": family(R, v, "ndcg10")}
                                                  for t, v in sorted(tr.items())}
                        share = {}
                        for s in R:
                            tot = new = 0
                            for k in range(3):
                                rq = runs[s][k]["queries"]
                                for q in qs:
                                    for c in rq[q][:10]:
                                        if c in L[q]["rel"]:
                                            tot += 1
                                            new += (q, c) in this
                            share[s] = {"relevant_top10": tot, "from_r9.2": new,
                                        "share": round(new / tot, 4) if tot else None}
                        block["share_relevant_top10_from_r9.2"] = share
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
    sq = sorted(q for q in Rall[BASE][0] if q in fired["b3"] and "wrapper" in (tt.get(q) or []))
    report["traps"]["b3_fired_wrapper_dev+facet_dev"] = {"n": len(sq), "ndcg10": family(Rall, sq, "ndcg10", arms=["b3"])}

    for split in ("known_dev", "ig_known_dev"):
        R, L = score(variants["low"], split, "exp2")
        qs = sorted(set(R[BASE][0]) & set(R["b1"][0]))
        block = {"n": len(qs)}
        for m in ("mrr2", "s10_2", "mrr", "success10"):
            block[m] = family(R, qs, m)
            block["levels_" + m] = level(R, qs, m)
        detail[split] = {s: {q: round(qmean(R[s], q, "mrr2"), 4) for q in qs} for s in R}
        subs = {"fired_b1": fired["b1"], "fired_b2": fired["b2"], "fired_b3": fired["b3"],
                "b3_top10_changed": t10["b3"], "q8_instant": {q for q in qs if q8path.get(q) == "instant"},
                "q8_rewrite": {q for q in qs if q8path.get(q) == "rewrite"},
                "fired_b1_instant": {q for q in fired["b1"] if q8path.get(q) == "instant"},
                "fired_b1_rewrite": {q for q in fired["b1"] if q8path.get(q) == "rewrite"}}
        for name, sub in subs.items():
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
                    else:
                        fac["no_creator_tag"].append(q)
                    for t in samp[q].get("traps", []) or ["none"]:
                        trp[t].append(q)
            report["facets"]["known_dev_s100"] = {t: {"n": len(v), "mrr2": family(R, v, "mrr2"),
                                                      "fired": {a: len(set(v) & fired[a]) for a in ARMS}}
                                                   for t, v in sorted(fac.items())}
            report["traps"]["known_dev_s100"] = {t: {"n": len(v), "mrr2": family(R, v, "mrr2")}
                                                  for t, v in sorted(trp.items())}
            b1s = {}
            for name, cond in (("creator_tagged", lambda q: samp[q].get("creator_mode") == "named"),
                               ("untagged", lambda q: not samp[q].get("creator_mode"))):
                sq = [q for q in qs if q in samp and q in fired["b1"] and cond(q)]
                b1s[name] = {"n": len(sq), "mrr2": family(R, sq, "mrr2", arms=["b1"])["b1"],
                             "s10_2": family(R, sq, "s10_2", arms=["b1"])["b1"]}
            report["b1_known_dev_sample_fired"] = b1s
        report["sets"][split] = {"exp2": block}

    # cost from meta
    cost = {s: {k + 1: runs[s][k]["meta"]["per_split"] for k in range(3)} for s in (BASE, *ARMS)}
    report["cost_meta"] = cost
    report["judges"] = json.load(open(os.path.join(W, "disagree_r9.2.json")))

    # verdict clauses
    prim = {"dev": ("dev", "low:lin4", "ndcg10"), "facet_dev": ("facet_dev", "low:lin4", "ndcg10"),
            "known_dev": ("known_dev", "exp2", "mrr2"), "ig_known_dev": ("ig_known_dev", "exp2", "mrr2")}
    verdict = {}
    for a in ARMS:
        v = {}
        for name, (s, key, m) in prim.items():
            d = report["sets"][s][key][m][a]
            v[name] = {"delta": d["delta"], "ci95": d["ci95"], "gain_rule": gain_rule(d, EXTRA_COST[a]),
                       "ni_point": d["delta"] >= -0.005, "ni_ci": d["ci95"][0] >= -0.03, "ni": ni(d),
                       "p_holm": d.get("p_holm"), "mde80": d["mde80"]}
        gains = [k for k, x in v.items() if x["gain_rule"]]
        adopted = any(gains) and all(x["ni"] for k, x in v.items() if k not in gains)
        verdict[a] = {"sets": v, "adopted": bool(adopted), "cheaper_equivalent": False}
    report["verdict"] = verdict
    json.dump(report, open(OUT_JSON, "w"), indent=1, default=lambda o: dict(o))
    json.dump(detail, open(os.path.join(W, "detail.json"), "w"), indent=1)
    print("wrote", OUT_JSON)


if __name__ == "__main__":
    main()
