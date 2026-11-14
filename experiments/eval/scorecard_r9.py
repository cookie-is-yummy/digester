"""PROTOTYPE ONLY - EVALUATOR SIDE. Round-9 Phase B: per-facet scorecard of Q8 in user terms (BRIEF-9 Phase B).

Reads $DIGESTER_DATA/evals/labels/ (evaluator only). Writes aggregates to --out (git) and per-search numbers to
--detail (under data/, gitignored). No paid calls.

User-terms metrics, per search (mean over the 3 repeats of a run):
  exact searches (this one item): hit10 = the target is on the first screen (top 10); hit5 = in the top 5.
  like searches (anything like it):
    good5_ai    - at least one good-or-exact item (grade >= 2 of 4; 2 of 3) in the top 5, on the merged labels
                  (pooled AI grades, two-judge lower-grade rule on 4-point rows; Derrick's target counts);
    good5_floor - the same with Derrick's own grades only (his target, his calibration grades): a lower bound;
    tgt10       - Derrick's own target is on the first screen (sets where he wrote the search for an item);
    good10_ai   - share of the first screen (top 10) that is good or exact, merged labels;
    good10_anch - Derrick-anchored share of the first screen that is good: items he graded count as he graded
                  them, every other in-library item counts P(Derrick says 2 | its AI grade), estimated on his 72
                  calibration items (3-point rows: the round-8 grade on his sheet; 4-point rows: the two-judge lower
                  grade, rubric j9-v1). Linear, so it needs no independence assumption;
    good5_indep - 1 - prod(1 - p_i) over the top 5 with the same p's. Assumes independent errors within a search;
                  correlated errors make the truth lower, so read it as an upper reading. JSON only.
  sat  = hit10 on exact searches, good5_ai on like searches ("the search worked on the first screen").
  gate = hit5 on exact searches, good5_ai on like searches (docs/08 Gate 1 wording: right item in the top 5).
CIs are 95% bootstraps over searches (the anchored metrics also resample the 72 calibration items). MDE is for a
paired Q8-vs-arm difference: (t.975 + t.80) * sd_d / sqrt(n), with sd_d from Q8 - H0r8 on the same cell (falling
back to the set's sd_d when the cell's sd_d is 0, flagged).

usage: scorecard_r9.py --out experiments/results/r9-scorecard.json --detail data/all/eval_work/r9.B/scorecard_detail.json
"""
import argparse
import collections
import json
import os
import sys

import numpy as np
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from corpus import DATA

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import judges9

LAB = os.path.join(DATA, "evals", "labels")
RUNS = os.path.join(DATA, "runs")
FACETS = ["creator", "creator_named", "creator_described", "topic", "type", "looks", "sound", "said", "tone",
          "examples", "when", "platform"]
DEV_EXACT = {"ig_hk_tailor", "ig_instant_pot", "ig_gun_trend"}  # BRIEF.md's single-answer dev searches
B = 2000


def jl(p):
    return [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]


def plat_map():
    out = {}
    for line in open(os.path.join(DATA, "corpus", "items.jsonl"), encoding="utf-8"):
        it = json.loads(line)
        out[it["dedup_key"].split(":", 1)[1]] = it["platform"]
    return out


def calibration():
    """Rows (derrick_grade, ai3, comb4) for the 72 items; comb4 = two-judge lower grade under j9-v1."""
    sheet = judges9.read_sheet(os.path.join(DATA, "eval_work", "r9", "sheet_cal72.jsonl"))
    gs = judges9.grades_of(sheet, "j9-v1")
    return [(r["derrick"], r["ai_r8"], judges9.combine_grade(g["A"], g["B"], "low"), r["query_id"], r["code"])
            for r, g in zip(sheet, gs)]


def ptables(cal):
    """P(Derrick 2 | AI grade): '3pt' over the round-8 grade 0..2, '4pt' over the two-judge grade 0..3."""
    out = {}
    for name, idx, k in (("3pt", 1, 3), ("4pt", 2, 4)):
        t = []
        for g in range(k):
            sel = [c[0] for c in cal if c[idx] == g]
            t.append(float(np.mean([d == 2 for d in sel])) if sel else 0.0)
        out[name] = t
    return out


def tag_sets():
    tags = json.load(open(os.path.join(DATA, "eval_work", "r9_audit", "tags.json")))
    out = {}
    for s, d in tags.items():
        for q, v in d.items():
            f = set(v.get("facets") or [])
            out[(s, q)] = (f, v.get("creator_mode"), v.get("specificity"), v.get("mlt"))
    return out


def facets_for(fs, mode):
    fs = set(fs)
    if "creator" in fs:
        fs.add("creator_described" if mode == "described" else "creator_named")
    return fs


def load_sets():
    split = json.load(open(os.path.join(DATA, "evals", "split.json")))
    lab = {r["id"]: r for r in jl(os.path.join(LAB, "evalset.jsonl"))}
    tags = tag_sets()
    cal = json.load(open(os.path.join(LAB, "derrick_inputs", "derrick-labels-2026-11-08.json")))["calibration"]
    dcal = collections.defaultdict(dict)
    for c in cal:
        dcal[c["query_id"]][c["code"]] = 1 if c["grade"] == 2 else 0
    seed = {}
    for fn in ("ig_real.jsonl", "facet_real.jsonl"):
        for r in jl(os.path.join(LAB, fn)):
            d = {c: 1 for c, g in r["relevant"].items() if g >= 2}
            d.update({c: 0 for c in r.get("judged_nonrelevant", [])})
            seed[r["id"]] = d
    sets = {
        "dev": {"q8": ("r8.5", "q8"), "h0": ("r8.1", "h0r8"), "tagkey": "dev"},
        "known_dev": {"q8": ("r8.5", "q8"), "h0": ("r8.1", "h0r8"), "tagkey": "known_dev_s100"},
        "ig_real": {"q8": ("r9", "q8_ig_real"), "h0": ("r9", "h0r8_ig_real"), "tagkey": "ig_real"},
        "facet_dev": {"q8": ("r9", "q8_facet_dev"), "h0": ("r9", "h0r8_facet_dev"), "tagkey": "facet_dev"},
    }
    for s, cfg in sets.items():
        qs = {}
        for q in split[s]:
            r = lab[q]
            scale = "4pt" if r.get("grade_scale") else "3pt"
            rel = {c: int(g) for c, g in r["relevant"].items() if g > 0}
            if s == "known_dev":
                spec = "exact"
            elif s == "dev":
                spec = "exact" if q in DEV_EXACT else ("mlt" if "more_like_this" in r["kinds"] else "like")
            elif s == "ig_real":
                spec = "exact" if r.get("search_kind") == "known_item" else "like"
            else:
                spec = r.get("specificity", "like")
            t = tags.get((cfg["tagkey"], q))
            if s == "facet_dev":  # Derrick's own ticks are ground truth here; creator mode from the tagger
                fs = facets_for(r.get("facets") or [], t[1] if t else None)
            elif t:
                fs = facets_for(t[0], t[1])
            else:
                fs = None  # known_dev outside the 100-search tagged sample, or a more-like-this dev search
            qs[q] = {"scale": scale, "rel": rel, "spec": spec, "facets": fs, "scope": r["scope"],
                     "derrick": {**dcal.get(q, {}), **seed.get(q, {})},
                     "target": {c for c in (seed.get(q) or {}) if seed[q][c]} or {c for c, g in rel.items() if g >= 2}}
        cfg["qs"] = qs
    return sets


def per_search(ranked, q, plat):
    """Returns exact-hit numbers and, for like searches, the top-5 grade classes for the anchored estimate."""
    pos = {}
    for i, c in enumerate(ranked):
        pos.setdefault(c, i)
    first_t = min((pos[c] for c in q["target"] if c in pos), default=None)
    out = {"hit10": float(first_t is not None and first_t < 10), "hit5": float(first_t is not None and first_t < 5)}
    top5 = ranked[:5]
    good_ai = any(q["rel"].get(c, 0) >= 2 for c in top5)
    d = q["derrick"]
    floor = any(d.get(c) == 1 for c in top5)
    counts5 = [0, 0, 0, 0]  # AI grade classes of top-5 items Derrick did not grade (in library)
    counts10 = [0, 0, 0, 0]
    dgood10 = 0
    for i, c in enumerate(ranked[:10]):
        if c in d:
            dgood10 += d[c]
            continue
        if c not in plat:
            continue
        g = q["rel"].get(c, 0)
        counts10[g] += 1
        if i < 5:
            counts5[g] += 1
    good10_ai = sum(1 for c in ranked[:10] if q["rel"].get(c, 0) >= 2) / 10
    out.update({"good5_ai": float(good_ai), "good5_floor": float(floor), "c5": counts5, "c10": counts10,
                "dgood10": dgood10, "good10_ai": good10_ai})
    return out


def anch(x, p):
    if x["good5_floor"]:
        return 1.0
    return 1.0 - float(np.prod([(1 - p[g]) ** n for g, n in enumerate(x["c5"]) if g < len(p)]))


def exp_good10(x, p):
    return x["dgood10"] + sum(p[g] * n for g, n in enumerate(x["c10"]) if g < len(p))


def load_run(rundir, stem):
    return [json.load(open(os.path.join(RUNS, rundir, f"{stem}_r{k}.json")))["queries"] for k in (1, 2, 3)]


def mde(sd, n):
    if n < 2:
        return None
    return float((stats.t.ppf(0.975, n - 1) + stats.t.ppf(0.80, n - 1)) * sd / np.sqrt(n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--detail", required=True)
    a = ap.parse_args()
    plat = plat_map()
    cal = calibration()
    P = ptables(cal)
    sets = load_sets()
    rng = np.random.default_rng(9)
    cal_boot = []
    for _ in range(B):
        idx = rng.integers(0, len(cal), len(cal))
        cal_boot.append(ptables([cal[i] for i in idx]))
    report = {"round": "r9.B", "calibration_p_good": P, "calibration_n": len(cal),
              "calibration_n_by_grade": {"3pt": [sum(1 for c in cal if c[1] == g) for g in range(3)],
                                         "4pt": [sum(1 for c in cal if c[2] == g) for g in range(4)]},
              "sets": {}}
    detail = {}
    for s, cfg in sets.items():
        qs = cfg["qs"]
        runs = {m: load_run(*cfg[m]) for m in ("q8", "h0")}
        per = {}  # (method, q) -> list over repeats
        for m, reps in runs.items():
            for q, lab in qs.items():
                if not lab["target"] and lab["spec"] == "exact":
                    continue
                if not lab["rel"] and not lab["derrick"]:
                    continue
                per[(m, q)] = [per_search(r.get(q, []), lab, plat) for r in reps]

        def val(m, q, metric, ptab):
            xs = per[(m, q)]
            p = ptab[qs[q]["scale"]]
            ex = qs[q]["spec"] == "exact"
            if metric == "good5_indep":
                return float(np.mean([anch(x, p) for x in xs]))
            if metric == "sat":
                return float(np.mean([x["hit10"] if ex else x["good5_ai"] for x in xs]))
            if metric == "gate":
                return float(np.mean([x["hit5"] if ex else x["good5_ai"] for x in xs]))
            if metric == "good10_anch":
                return float(np.mean([exp_good10(x, p) / 10 for x in xs]))
            if metric == "tgt10":
                return float(np.mean([x["hit10"] for x in xs]))
            return float(np.mean([x[metric] for x in xs]))

        groups = {"all": [q for q in qs if qs[q]["spec"] != "mlt"], "exact": [], "like": [],
                  "ig": [], "yt": []}
        for q, lab in qs.items():
            if lab["spec"] == "mlt" or ("q8", q) not in per:
                continue
            groups[lab["spec"]].append(q)
            groups[lab["scope"]].append(q) if lab["scope"] in ("ig", "yt") else None
            for f in lab["facets"] or []:
                groups.setdefault(f, []).append(q)
            if lab["facets"] is not None:
                groups.setdefault("tagged", []).append(q)
        groups["all"] = [q for q in groups["all"] if ("q8", q) in per]
        has_seed = s in ("ig_real", "facet_dev")
        metrics = {"exact": ["hit10", "hit5"],
                   "like": ["good5_ai", "good5_floor"] + (["tgt10"] if has_seed else [])
                   + ["good10_ai", "good10_anch", "good5_indep"]}
        out = {}
        set_sd = {}
        for gname in ["all"] + [g for g in groups if g != "all"]:
            gq = groups[gname]
            cell = {"n": len(gq), "n_exact": sum(qs[q]["spec"] == "exact" for q in gq),
                    "n_like": sum(qs[q]["spec"] == "like" for q in gq),
                    "n_ig": sum(qs[q]["scope"] == "ig" for q in gq)}
            if len(gq) < 3:
                out[gname] = {**cell, "suppressed": "n < 3"}
                continue
            mlist = ["sat", "gate"]
            if cell["n_exact"] >= 3:
                mlist += metrics["exact"]
            if cell["n_like"] >= 3:
                mlist += metrics["like"]
            for metric in mlist:
                sub = gq
                if metric in metrics["exact"]:
                    sub = [q for q in gq if qs[q]["spec"] == "exact"]
                elif metric in metrics["like"]:
                    sub = [q for q in gq if qs[q]["spec"] == "like"]
                v8 = np.array([val("q8", q, metric, P) for q in sub])
                v0 = np.array([val("h0", q, metric, P) for q in sub])
                d = v8 - v0
                idx = rng.integers(0, len(sub), (B, len(sub)))
                if metric in ("good5_indep", "good10_anch"):
                    bs = []
                    for b in range(B):
                        pb = cal_boot[b]
                        bs.append(np.mean([val("q8", sub[i], metric, pb) for i in idx[b]]))
                    bs = np.array(bs)
                else:
                    bs = v8[idx].mean(axis=1)
                sd = float(d.std(ddof=1)) if len(sub) > 1 else 0.0
                if gname == "all":
                    set_sd[metric] = sd
                fb = False
                if sd == 0 and set_sd.get(metric):
                    sd, fb = set_sd[metric], True
                cell[metric] = {"n": len(sub), "q8": round(float(v8.mean()), 3),
                                "ci95": [round(float(np.percentile(bs, 2.5)), 3),
                                         round(float(np.percentile(bs, 97.5)), 3)],
                                "h0r8": round(float(v0.mean()), 3), "d_vs_h0r8": round(float(d.mean()), 3),
                                "sd_d": round(sd, 3), "mde": None if (sd == 0 or mde(sd, len(sub)) is None) else round(mde(sd, len(sub)), 3),
                                "sd_d_from_set": fb}
            out[gname] = cell
        report["sets"][s] = out
        detail[s] = {q: {m: round(val("q8", q, m, P), 4) for m in ("sat", "gate", "hit10", "good5_ai", "good5_floor",
                                                                    "good10_anch")}
                     for q in groups["all"]}
    json.dump(report, open(a.out, "w"), indent=1)
    json.dump(detail, open(a.detail, "w"), indent=1)
    for s, out in report["sets"].items():
        for g, c in out.items():
            if "sat" in c:
                line = f"{s:10s} {g:18s} n{c['n']:4d} ex{c['n_exact']:4d} sat {c['sat']['q8']:.3f} {c['sat']['ci95']} mde {c['sat']['mde']}"
                for m in ("hit10", "good5_ai", "good5_floor", "tgt10", "good10_anch"):
                    if m in c:
                        line += f" | {m} {c[m]['q8']:.3f} {c[m]['ci95']} h0 {c[m]['h0r8']:.3f} mde {c[m]['mde']}"
                print(line)
            else:
                print(f"{s:10s} {g:18s} n{c['n']:4d} suppressed")
    print("P(good | AI grade):", P, report["calibration_n_by_grade"])


if __name__ == "__main__":
    main()
