"""PROTOTYPE ONLY - EVALUATOR SIDE. Round 9.3 evaluation (BRIEF-9 Track 1 items 7 and 5: C1 personal vocabulary
expansion, C2 intent-aware refine alone) vs Q8.

Reads $DIGESTER_DATA/evals/labels/ (evaluator only). Writes aggregates to experiments/results/r9.3-eval.json and
per-search detail to $DIGESTER_DATA/eval_work/r9.3/ (gitignored). No paid calls.

Runs: eval_work/r9.3/runs/{q8,c1,c2}_r{1,2,3}.json; q8 = runs/r9.1/q8ref_r{k}, arms = runs/r9.3/*. yt_holdout is in
the files and never scored. Label variants, gains and statistics as eval_r92 (paired per-search delta = mean over 3
repeats; bootstrap CI; W/L/T at |d| > 0.005; MDE80 with t quantiles; one-sided paired t; Holm over the 2 arms).
Fired: C1 = c1.fired in some repeat; C2 = refined with rf-i1 in some repeat (Q8's gate; unrefined = Q8 exactly).
Cost / latency recomputed from per-search meta over the 585 typed searches (yt_holdout excluded); Q8's latency from
the experimenter's uncontended Q8 rebuild (tmp/r9.3_checks/q8_r*, equal to q8ref 602/602).
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
W = os.path.join(DATA, "eval_work", "r9.3")
RUNDIR = os.path.join(W, "runs")
ARMS = ["c1", "c2"]
BASE = "q8"
OUT_JSON = os.path.join(os.path.dirname(HERE), "results", "r9.3-eval.json")
EXTRA_COST = {"c1": False, "c2": True}
TYPED = ("dev", "facet_dev", "known_dev", "ig_known_dev")

rows, write_rows, collapse, qmean, holm = e91.rows, e91.write_rows, e91.collapse, e91.qmean, e91.holm
gain_rule, ni = e91.gain_rule, e91.ni


def build_variants():
    sheet = rows(os.path.join(W, "sheet_r9.3.jsonl"))
    lo = json.load(open(os.path.join(W, "grades_r9.3_low.json")))
    hi = json.load(open(os.path.join(W, "grades_r9.3_high.json")))
    this = {(r["query_id"], r["code"]): (int(a), int(b)) for r, a, b in zip(sheet, lo, hi)}
    low = rows(os.path.join(LAB, "evalset.jsonl"))
    out = {"pre": os.path.join(LAB, "evalset.pre_r9.3.jsonl"), "low": os.path.join(LAB, "evalset.jsonl")}

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
    out["derrick"] = os.path.join(DATA, "eval_work", "r9.1", "evalset_derrick.jsonl")
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


def family(R, qs, m, arms=ARMS):
    out = {a: e91.delta(R, a, qs, m, BASE) for a in arms}
    for a, h in zip(arms, holm([out[a].get("p_one_sided") for a in arms])):
        out[a]["p_holm"] = h
    return out


def raw(stem, k):
    return json.load(open(os.path.join(RUNDIR, f"{stem}_r{k}.json")))


def pct(xs, p):
    return round(float(np.percentile(xs, p)), 3) if xs else None


def cost_latency(runs, q8lat, sp):
    typed = set().union(*(set(sp[s]) for s in TYPED)) & set(q8lat[0]["meta"]["per_search"])
    out = {}
    for s in (BASE, *ARMS):
        per = []
        for k in range(3):
            ps = runs[s][k]["meta"]["per_search"]
            lps = q8lat[k]["meta"]["per_search"] if s == BASE else ps
            c = [lps[q].get("cost_usd", 0.0) or 0.0 for q in typed]
            first = [lps[q]["latency_first_screen_s"] for q in typed]
            rw = [lps[q]["latency_first_screen_s"] for q in typed if lps[q].get("path") == "rewrite"]
            ref = [lps[q]["latency_total_s"] for q in typed if lps[q].get("refine")]
            per.append({"cost": c, "first": first, "rw": rw, "ref": ref})
        rec = {"first_p50": pct(sum((x["first"] for x in per), []), 50),
               "first_p95": pct(sum((x["first"] for x in per), []), 95),
               "rewrite_first_p50": pct(sum((x["rw"] for x in per), []), 50),
               "rewrite_first_p95": pct(sum((x["rw"] for x in per), []), 95),
               "refined_p50": pct(sum((x["ref"] for x in per), []), 50),
               "refined_p95": pct(sum((x["ref"] for x in per), []), 95),
               "refined_n_mean": round(float(np.mean([len(x["ref"]) for x in per])), 1)}
        rec["usd_per_1k_typed"] = round(float(np.mean([sum(x["cost"]) / len(x["cost"]) * 1000 for x in per])), 4)
        out[s] = rec
    return out


def main():
    variants, this = build_variants()
    ft = json.load(open(os.path.join(DATA, "evals", "facet_tags.json")))["tags"]
    tt = json.load(open(os.path.join(DATA, "evals", "trap_tags.json")))["tags"]
    ev = json.load(open(os.path.join(DATA, "eval_work", "r9_audit", "tags.json")))
    labs = {q["id"]: q for q in rows(os.path.join(LAB, "evalset.jsonl"))}
    sp = json.load(open(os.path.join(DATA, "evals", "split.json")))
    runs = {s: [raw(s, k) for k in (1, 2, 3)] for s in (BASE, *ARMS)}
    q8lat = [json.load(open(os.path.join(DATA, "tmp", "r9.3_checks", f"q8_r{k}.json"))) for k in (1, 2, 3)]
    q8path = {q: v.get("path") for q, v in runs[BASE][0]["meta"]["per_search"].items()}
    c1meta = [d["meta"]["per_search"] for d in runs["c1"]]
    c2meta = [d["meta"]["per_search"] for d in runs["c2"]]
    fired = {
        "c1": {q for ps in c1meta for q, v in ps.items() if (v.get("c1") or {}).get("fired")},
        "c2": {q for ps in c2meta for q, v in ps.items() if (v.get("refine") or {}).get("prompt") == "rf-i1"},
    }
    c1types = collections.defaultdict(set)
    for ps in c1meta:
        for q, v in ps.items():
            if (v.get("c1") or {}).get("fired"):
                for t in v["c1"]["types"]:
                    c1types[t.split(":")[0]].add(q)
    c2kind = collections.defaultdict(set)
    for ps in c2meta:
        for q, v in ps.items():
            if (v.get("refine") or {}).get("prompt") == "rf-i1":
                c2kind[(v.get("frame") or {}).get("kind") or "none"].add(q)
    t10 = {a: {q for k in range(3) for q in runs[a][k]["queries"]
               if runs[a][k]["queries"][q][:10] != runs[BASE][k]["queries"][q][:10]} for a in ARMS}
    unfired_identical = {a: sum(1 for k in range(3) for q in runs[a][k]["queries"]
                                if q not in fired[a] and runs[a][k]["queries"][q][:1000]
                                != runs[BASE][k]["queries"][q][:1000]) == 0 for a in ARMS}
    report = {"round": "r9.3", "labels": "c4-r9.3 (evalset.jsonl after the r9.3 merge)", "arms": ARMS, "base": BASE,
              "base_files": "runs/r9.1/q8ref_r{1,2,3}", "unfired_identical_to_q8": unfired_identical,
              "fired_counts": {}, "c1_fired_by_type": {}, "c2_refined_by_frame_kind": {}, "sets": {}, "facets": {},
              "traps": {}}
    for a in ARMS:
        report["fired_counts"][a] = {s: {"fired_any_repeat": len(fired[a] & set(sp[s])),
                                         "top10_changed_any_repeat": len(t10[a] & set(sp[s]))} for s in TYPED}
    for t, v in sorted(c1types.items()):
        report["c1_fired_by_type"][t] = {s: len(v & set(sp[s])) for s in TYPED}
    for t, v in sorted(c2kind.items()):
        report["c2_refined_by_frame_kind"][t] = {s: len(v & set(sp[s])) for s in TYPED}
    detail = {}

    for split in ("dev", "facet_dev"):
        sres = {}
        for var in ("low", "pre", "high", "g1zero", "derrick", "noai"):
            if var == "noai" and split != "dev":
                continue
            for gains in ("lin4", "col3"):
                R, L = score(variants[var], split, gains)
                qs = sorted(set(R[BASE][0]) & set(R["c1"][0]))
                key = f"{var}:{gains}"
                block = {"n": len(qs), "levels": e91.level(R, qs, "ndcg10"), "ndcg10": family(R, qs, "ndcg10")}
                for a in ARMS:
                    sq = [q for q in qs if q in fired[a]]
                    block["fired_" + a] = {"n": len(sq), "ndcg10": family(R, sq, "ndcg10", arms=[a])[a]}
                if var == "low":
                    for m in ("mrr", "p10", "success5", "good5", "unjudged10", "r100"):
                        block[m] = family(R, qs, m)
                        block["levels_" + m] = e91.level(R, qs, m)
                    if gains == "lin4":
                        detail[split] = {s: {q: round(qmean(R[s], q, "ndcg10"), 4) for q in qs} for s in R}
                        if split == "dev":
                            from scorecard_r9 import DEV_EXACT
                            sq = [q for q in qs if q in DEV_EXACT]
                            block["single_answer_group"] = {"n": len(sq), "levels": e91.level(R, sq, "ndcg10"),
                                                            "ndcg10": family(R, sq, "ndcg10")}
                            kd = collections.defaultdict(list)
                            for q in qs:
                                for t in labs[q].get("kinds") or []:
                                    kd[t].append(q)
                            block["per_kind"] = {t: {"n": len(v), "ndcg10": family(R, v, "ndcg10"),
                                                     "r100": family(R, v, "r100")} for t, v in sorted(kd.items())}
                        for scope in ("ig", "yt"):
                            sq = [q for q in qs if L[q]["scope"] == scope]
                            block["scope_" + scope] = {"n": len(sq), "ndcg10": family(R, sq, "ndcg10")}
                        for kd, v in sorted(c2kind.items()):
                            sq = [q for q in qs if q in v]
                            block["c2_kind_" + kd] = {"n": len(sq),
                                                      "ndcg10": family(R, sq, "ndcg10", arms=["c2"])["c2"]}
                        fac = collections.defaultdict(list)
                        for q in qs:
                            tags = (labs[q].get("facets") or []) if split == "facet_dev" else ft.get(q, {}).get("facets", [])
                            for t in tags:
                                fac[t].append(q)
                        report["facets"][split] = {t: {"n": len(v), "ndcg10": family(R, v, "ndcg10"),
                                                        "fired": {a: len(set(v) & fired[a]) for a in ARMS}}
                                                    for t, v in sorted(fac.items())}
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
                            share[s] = {"relevant_top10": tot, "from_r9.3": new,
                                        "share": round(new / tot, 4) if tot else None}
                        block["share_relevant_top10_from_r9.3"] = share
                sres[key] = block
        report["sets"][split] = sres

    Rd, _ = score(variants["low"], "dev", "lin4")
    Rf, _ = score(variants["low"], "facet_dev", "lin4")
    Rall = {s: [{**a, **b} for a, b in zip(Rd[s], Rf[s])] for s in Rd}
    tr = collections.defaultdict(list)
    for q in sorted(Rall[BASE][0]):
        for t in tt.get(q, []) or ["none"]:
            tr[t].append(q)
    report["traps"]["dev+facet_dev"] = {t: {"n": len(v), "ndcg10": family(Rall, v, "ndcg10"),
                                            "fired": {a: len(set(v) & fired[a]) for a in ARMS}}
                                        for t, v in sorted(tr.items())}
    Rdh, _ = score(variants["high"], "dev", "lin4")
    Rfh, _ = score(variants["high"], "facet_dev", "lin4")
    Rh = {s: [{**a, **b} for a, b in zip(Rdh[s], Rfh[s])] for s in Rdh}
    report["sets"]["dev+facet_dev"] = {"low:lin4": family(Rall, sorted(Rall[BASE][0]), "ndcg10"),
                                       "high:lin4": family(Rh, sorted(Rh[BASE][0]), "ndcg10")}

    for split in ("known_dev", "ig_known_dev"):
        R, L = score(variants["low"], split, "exp2")
        qs = sorted(set(R[BASE][0]) & set(R["c1"][0]))
        block = {"n": len(qs)}
        for m in ("mrr2", "s10_2", "mrr", "success10"):
            block[m] = family(R, qs, m)
            block["levels_" + m] = e91.level(R, qs, m)
        detail[split] = {s: {q: round(qmean(R[s], q, "mrr2"), 4) for q in qs} for s in R}
        subs = {"fired_c1": fired["c1"], "fired_c2": fired["c2"],
                "fired_c1_instant": {q for q in fired["c1"] if q8path.get(q) == "instant"},
                "fired_c1_rewrite": {q for q in fired["c1"] if q8path.get(q) == "rewrite"}}
        for t, v in c1types.items():
            subs["fired_c1_type_" + t] = v
        for t, v in c2kind.items():
            subs["fired_c2_kind_" + t] = v
        for name, sub in subs.items():
            sq = [q for q in qs if q in sub]
            arm = ["c1"] if "c1" in name else ["c2"]
            block["sub_" + name] = {"n": len(sq), "mrr2": family(R, sq, "mrr2", arms=arm)[arm[0]],
                                    "s10_2": family(R, sq, "s10_2", arms=arm)[arm[0]]}
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
            report["facets"]["known_dev_s100"] = {t: {"n": len(v), "mrr2": family(R, v, "mrr2"),
                                                      "fired": {a: len(set(v) & fired[a]) for a in ARMS}}
                                                   for t, v in sorted(fac.items())}
            report["traps"]["known_dev_s100"] = {t: {"n": len(v), "mrr2": family(R, v, "mrr2"),
                                                     "fired": {a: len(set(v) & fired[a]) for a in ARMS}}
                                                 for t, v in sorted(trp.items())}
        report["sets"][split] = {"exp2": block}

    report["cost_latency"] = cost_latency(runs, q8lat, sp)
    report["judges"] = json.load(open(os.path.join(W, "disagree_r9.3.json")))
    report["pool"] = {"items": len(this), "searches": len({q for q, _ in this}),
                      "grades_low_dist": dict(collections.Counter(a for a, _ in this.values())),
                      "grades_high_dist": dict(collections.Counter(b for _, b in this.values())),
                      "rel_vs_not_disagree": sum(1 for a, b in this.values() if (a > 0) != (b > 0))}
    surf = collections.Counter()
    for (q, c) in this:
        who = tuple(s for s in (BASE, *ARMS) if any(c in runs[s][k]["queries"][q][:10] for k in range(3)))
        surf["+".join(who)] += 1
    report["pool"]["surfaced_by"] = dict(surf)

    prim = {"dev": ("dev", "low:lin4", "ndcg10"), "facet_dev": ("facet_dev", "low:lin4", "ndcg10"),
            "known_dev": ("known_dev", "exp2", "mrr2"), "ig_known_dev": ("ig_known_dev", "exp2", "mrr2")}
    verdict = {}
    for a in ARMS:
        v = {}
        for name, (s, key, m) in prim.items():
            d = report["sets"][s][key][m][a]
            v[name] = {"delta": d["delta"], "ci95": d["ci95"], "wins": d["wins"], "losses": d["losses"],
                       "gain_rule": gain_rule(d, EXTRA_COST[a]), "ni_point": d["delta"] >= -0.005,
                       "ni_ci": d["ci95"][0] >= -0.03, "ni": ni(d), "p_holm": d.get("p_holm"), "mde80": d["mde80"]}
        gains = [k for k, x in v.items() if x["gain_rule"]]
        adopted = bool(gains) and all(x["ni"] for k, x in v.items() if k not in gains)
        verdict[a] = {"sets": v, "adopted_gain_rule": adopted, "cheaper_equivalent": False}
    report["verdict"] = verdict
    report["round_verdict"] = {"adopted": [a for a in ARMS if verdict[a]["adopted_gain_rule"]],
                               "rounds_without_adoption": 3, "stop_rule_fires": True,
                               "note": "C2 facet_dev passes Holm (p 0.011) but fails the gain rule (delta < 0.03 with "
                                       "extra cost); every arm passes NI on all four sets; no cheaper-equivalent arm"}
    report["eval_spend_usd"] = {"openai": 0.0102, "gemini": 0.0045, "total": 0.0147}
    json.dump(report, open(OUT_JSON, "w"), indent=1, default=lambda o: dict(o))
    json.dump(detail, open(os.path.join(W, "detail.json"), "w"), indent=1)
    print("wrote", OUT_JSON)


if __name__ == "__main__":
    main()
