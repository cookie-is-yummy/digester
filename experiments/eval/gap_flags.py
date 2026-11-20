"""PROTOTYPE ONLY - EVALUATOR SIDE. Round 2, Q1: do the per-facet gap flags predict what search misses?

Only the evaluator role runs this file: it reads data/evals/labels/ (dev split only) and, for step 3, the
evaluator's MU reading in data/eval_work/refcmp/ plus the Muse export. Builders get only the aggregate note
experiments/results/r2-q1-gap-flags.{md,json}. Per-pair detail goes to data/eval_work/r2q1/ (gitignored).

Steps (experiments/BRIEF-2.md, Q1):
1. Search kind -> facets (KIND_FACETS). A search uses the union of the facets of all its kinds; kinds with no
   mapping (time, structure) are ignored. Sensitivity: first mapped kind only.
2. Every (dev search, right answer) pair under B3 (e20_hyde_b2_r{1,2,3}); found = rank < max(50, 2 x answers).
   AUC for predicting a miss from (a) facet listed unknown, (b) facet empty, (c) hedge (listed unknown but
   filled), (d) round-0 caption-richness score (ported from archive/2026-10-30-searchlab/info_bench.py:
   6 query-independent features, logistic regression, 5-fold CV). Pair score for (a)-(c) = share of the
   search's facets with the flag. AUC per repeat, then the mean; CI = bootstrap over searches.
3. Flag accuracy vs the evaluator's MU reading (refcmp judged.jsonl, n = 126 read items) per facet.
4. Rank of each missed answer (median over repeats): top 200 / 201-1000 / not in the stored top 1000.
5. Media gate: rule-based selection per rung; corpus share, cost per 1,000 items at lib/ai_prices.json
   prices, share of current misses covered; vs "everything" and "on-demand only".

Facet state of an item (te-v1c, last valid row per code):
- unknown: facet listed in `unknown` (topics listed as "topics").
- empty: field has no value after the enrichment's own FILLER filtering (re-applied here). kind: other/unknown.
  audio (no field): not named anywhere, the same regex as reference_compare.py (_audio_named).
- hedge: listed unknown but filled.
Items with no enrichment row (friends' items) count as unknown and empty on every facet.

usage: python experiments/eval/gap_flags.py
"""

import collections
import json
import os
import re
import statistics
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(EXP, "lib"))
from common import STOP, info_class, strip_tags  # noqa: E402
from corpus import DATA, Corpus, code_of  # noqa: E402
from score_run import load_labels  # noqa: E402

RUNS = [os.path.join(DATA, "runs", f"e20_hyde_b2_r{k}.json") for k in (1, 2, 3)]
ENRICH = os.path.join(DATA, "enrich", "te-v1c_gemini-3.1-flash-lite.jsonl")
WORK = os.path.join(DATA, "eval_work", "r2q1")
REFCMP = os.path.join(DATA, "eval_work", "refcmp")
OUT_JSON = os.path.join(EXP, "results", "r2-q1-gap-flags.json")
PRICES = os.path.join(EXP, "lib", "ai_prices.json")

KIND_FACETS = {
    "place": ["place"],
    "said_shown": ["said", "shown"],
    "audio": ["audio"],
    "vibe": ["vibe"],
    "people": ["people"],
    "task": ["use"],
    "topic": ["topics", "kind"],
    "name": ["topics", "kind"],
    "more_like_this": ["shown", "vibe"],
}
FIELD = {f: f for f in ["topics", "shown", "said", "place", "people", "vibe", "use"]}
ALL_FACETS = ["kind", "topics", "shown", "said", "audio", "place", "people", "vibe", "use"]
FILLER = re.compile(r"^(unknown|none|n/?a|not (specified|stated|mentioned|applicable)|unspecified)$|\bunknown\b|"
                    r"not specified|^(country|region|country/region|worldwide)$|\bcontext$")
LISTS = ["topics", "shown", "said", "place", "people", "vibe", "use", "queries"]
AUDIO_OURS = (r"\b(music\w*|songs?|track|beat|lyrics|sounds?|audio|soundtrack|sing\w*|melod\w*|tune|asmr|"
              r"music_dance|remix|album|band|rapper|dj)\b")


# ---------------------------------------------------------------- loading
def load_enrich():
    out = {}
    for ln in open(ENRICH, encoding="utf-8"):
        r = json.loads(ln)
        if r.get("ok"):
            out[r["code"]] = r  # last valid row wins
    return out


def load_items():
    items, weight = {}, collections.defaultdict(float)
    for ln in open(os.path.join(DATA, "corpus", "items.jsonl"), encoding="utf-8"):
        it = json.loads(ln)
        items[code_of(it)] = it
    id2code = {it["id"]: c for c, it in items.items()}
    for ln in open(os.path.join(DATA, "corpus", "interactions.jsonl"), encoding="utf-8"):
        r = json.loads(ln)
        c = id2code.get(r["item_id"])
        if c:
            weight[c] = max(weight[c], float(r.get("weight") or 0))
    return items, dict(weight)


def vals(e, f):
    return [x for x in (e.get(f) or []) if x and not FILLER.search(str(x))]


def audio_named(e):
    txt = " ".join([e.get("summary") or "", e.get("kind") or ""] + [x for f in LISTS for x in (e.get(f) or [])])
    return bool(re.search(AUDIO_OURS, txt, re.IGNORECASE))


def facet_state(e, f):
    """(unknown, empty, hedge) for item enrichment e (None = not enriched)."""
    if e is None:
        return True, True, False
    unk = f in set(e.get("unknown") or [])
    if f == "kind":
        empty = e.get("kind") in (None, "", "other", "unknown")
    elif f == "audio":
        empty = not audio_named(e)
    else:
        empty = not vals(e, FIELD[f])
    return unk, empty, unk and not empty


def search_facets(kinds, first_only=False):
    fs = []
    for k in kinds:
        if k in KIND_FACETS:
            fs += [f for f in KIND_FACETS[k] if f not in fs]
            if first_only:
                break
    return fs


# ---------------------------------------------------------------- caption richness (round 0, ported)
def richness_features(items, codes):
    """info_bench.py features for each code in `codes` (query independent)."""
    C = Corpus("bge_full")
    cv, _ = C.bm25_index("full")
    N = len(C.ids)
    docs_tf = cv.transform([C.text(n, "cap_tags").lower() for n in range(N)])
    df = np.asarray((docs_tf > 0).sum(axis=0)).ravel()
    idf = np.log((N + 1) / (df + 1))
    mean = C.V.mean(0)
    mean /= np.linalg.norm(mean)
    specific = 1 - C.V @ mean
    rng = np.random.default_rng(0)
    probe = C.V[rng.choice(N, 400, replace=False)]
    hub = np.zeros(N)
    for row in probe @ C.V.T:
        hub[np.argpartition(-row, 20)[:20]] += 1
    spec_med, hub_med = float(np.median(specific)), float(np.median(hub))
    feats, has_vec = [], []
    for c in codes:
        it = items[c]
        cap = strip_tags(it.get("caption") or "").lower()
        co = cv.transform([cap])
        co.data[:] = 1
        idf_info = float((co @ idf)[0])
        toks = re.findall(r"[a-z]{3,}", cap)
        words = len({t for t in toks if t not in STOP})
        tags = len([t for t in (it["platform_data"].get("hashtags") or []) if t.lower() not in STOP])
        n = C.by_code.get(c)
        has_vec.append(n is not None)
        feats.append([float(info_class(it) == "ok"), np.log1p(words), np.log1p(idf_info), np.log1p(tags),
                      float(specific[n]) if n is not None else spec_med,
                      -float(hub[n]) if n is not None else -hub_med])
    return np.array(feats), np.array(has_vec)


FEAT_NAMES = ["gate_ok", "content_words", "idf_info", "topical_tags", "specificity", "neg_hubness"]


# ---------------------------------------------------------------- helpers
def auc(y, s):
    y, s = np.asarray(y), np.asarray(s, dtype=float)
    if y.min() == y.max():
        return None
    return float(roc_auc_score(y, s))


def r3(x):
    return None if x is None else round(float(x), 3)


def boot_auc(pairs, key, label="miss", n=1000, seed=0):
    """Bootstrap over searches: resample searches, pool their pairs, AUC."""
    by_q = collections.defaultdict(list)
    for p in pairs:
        by_q[p["q"]].append(p)
    qs = sorted(by_q)
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        pick = rng.choice(len(qs), len(qs))
        ps = [p for i in pick for p in by_q[qs[i]]]
        a = auc([p[label] for p in ps], [p[key] for p in ps])
        if a is not None:
            out.append(a)
    return [r3(np.percentile(out, 2.5)), r3(np.percentile(out, 97.5))]


def ranks_of(run, q):
    return {c: i for i, c in enumerate(run["queries"].get(q, []))}


# ---------------------------------------------------------------- main
def main():
    os.makedirs(WORK, exist_ok=True)
    L = load_labels("dev")
    enr = load_enrich()
    items, weight = load_items()
    runs = [json.load(open(p)) for p in RUNS]
    R = {}

    # ---- step 1/2: pairs
    pairs = []
    for q, lab in sorted(L.items()):
        rel = lab["rel"]
        if not rel:
            continue
        K = max(50, 2 * len(rel))
        fs_all = search_facets(lab["kinds"])
        fs_first = search_facets(lab["kinds"], first_only=True)
        rk = [ranks_of(r, q) for r in runs]
        for c, g in rel.items():
            e = enr.get(c)
            st = {f: facet_state(e, f) for f in ALL_FACETS}
            ranks = [r.get(c) for r in rk]
            miss_r = [int(rr is None or rr >= K) for rr in ranks]
            p = {"q": q, "c": c, "grade": g, "kinds": lab["kinds"], "facets": fs_all, "K": K,
                 "ranks": ranks, "miss_r": miss_r, "miss": int(sum(miss_r) >= 2), "enriched": e is not None}
            for tag, fs in (("", fs_all), ("_first", fs_first)):
                p["unk" + tag] = float(np.mean([st[f][0] for f in fs])) if fs else 0.0
                p["empty" + tag] = float(np.mean([st[f][1] for f in fs])) if fs else 0.0
                p["hedge" + tag] = float(np.mean([st[f][2] for f in fs])) if fs else 0.0
            p["gap"] = float(np.mean([st[f][0] or st[f][1] for f in fs_all])) if fs_all else 0.0
            p["state"] = {f: list(map(int, st[f])) for f in ALL_FACETS}
            pairs.append(p)

    codes = sorted({p["c"] for p in pairs})
    F, has_vec = richness_features(items, codes)
    fidx = {c: i for i, c in enumerate(codes)}
    X = np.array([F[fidx[p["c"]]] for p in pairs])
    Xs = (X - X.mean(0)) / (X.std(0) + 1e-9)

    # (d): logistic regression on 'found', 5-fold CV, per repeat; richness score = P(found); miss score = 1 - P
    rich_r = []
    for k in range(3):
        y_found = np.array([1 - p["miss_r"][k] for p in pairs])
        clf = LogisticRegression(max_iter=2000, class_weight="balanced")
        pred = cross_val_predict(clf, Xs, y_found, cv=StratifiedKFold(5, shuffle=True, random_state=0),
                                 method="predict_proba")[:, 1]
        rich_r.append(1 - pred)
    for i, p in enumerate(pairs):
        p["rich_miss"] = float(np.mean([rr[i] for rr in rich_r]))
        p["rich_miss_r"] = [float(rr[i]) for rr in rich_r]
        for j, nm in enumerate(FEAT_NAMES):
            p["f_" + nm] = float(-X[i, j])  # higher feature = richer, so negate for 'miss'
        p["has_vec"] = bool(has_vec[fidx[p["c"]]])
    # flags + richness combined (CV), for reference
    comb_r = []
    for k in range(3):
        y_found = np.array([1 - p["miss_r"][k] for p in pairs])
        Z = np.column_stack([Xs, [[p["unk"], p["empty"], p["hedge"]] for p in pairs]])
        pred = cross_val_predict(LogisticRegression(max_iter=2000, class_weight="balanced"), Z, y_found,
                                 cv=StratifiedKFold(5, shuffle=True, random_state=0), method="predict_proba")[:, 1]
        comb_r.append(1 - pred)
    for i, p in enumerate(pairs):
        p["comb_miss_r"] = [float(rr[i]) for rr in comb_r]

    R["population"] = {
        "dev_searches": len({p["q"] for p in pairs}),
        "pairs": len(pairs),
        "pairs_grade2": sum(1 for p in pairs if p["grade"] == 2),
        "pairs_not_enriched": sum(1 for p in pairs if not p["enriched"]),
        "pairs_no_caption_vector": sum(1 for p in pairs if not p["has_vec"]),
        "pairs_with_no_mapped_facet": sum(1 for p in pairs if not p["facets"]),
        "miss_rate_per_repeat": [r3(np.mean([p["miss_r"][k] for p in pairs])) for k in range(3)],
        "miss_rate_majority": r3(np.mean([p["miss"] for p in pairs])),
        "miss_agreement_all3": r3(np.mean([len(set(p["miss_r"])) == 1 for p in pairs])),
    }

    def auc_block(ps):
        out = {"n_searches": len({p["q"] for p in ps}), "n_pairs": len(ps),
               "miss_rate": r3(np.mean([np.mean(p["miss_r"]) for p in ps]))}
        for name, key in [("a_unknown", "unk"), ("b_empty", "empty"), ("c_hedge", "hedge"), ("gap_unknown_or_empty", "gap"),
                          ("a_unknown_first_kind", "unk_first"), ("b_empty_first_kind", "empty_first"),
                          ("c_hedge_first_kind", "hedge_first")]:
            per = [auc([p["miss_r"][k] for p in ps], [p[key] for p in ps]) for k in range(3)]
            per = [x for x in per if x is not None]
            out[name] = r3(np.mean(per)) if per else None
            out[name + "_flag_rate"] = r3(np.mean([p[key] for p in ps]))
        for name, key in [("d_richness_cv", "rich_miss_r"), ("flags_plus_richness_cv", "comb_miss_r")]:
            per = [auc([p["miss_r"][k] for p in ps], [p[key][k] for p in ps]) for k in range(3)]
            per = [x for x in per if x is not None]
            out[name] = r3(np.mean(per)) if per else None
        # within-search AUC: per search (both classes present), pair-weighted mean; removes between-search effects
        by_q = collections.defaultdict(list)
        for p in ps:
            by_q[p["q"]].append(p)
        for name, key, rep in [("within_a_unknown", "unk", False), ("within_b_empty", "empty", False),
                               ("within_c_hedge", "hedge", False), ("within_d_richness_cv", "rich_miss_r", True)]:
            num = den = 0.0
            for q, qp in by_q.items():
                per = [auc([p["miss_r"][k] for p in qp], [(p[key][k] if rep else p[key]) for p in qp]) for k in range(3)]
                per = [x for x in per if x is not None]
                if per:
                    num += np.mean(per) * len(qp)
                    den += len(qp)
            out[name] = r3(num / den) if den else None
        out["within_n_searches_with_both_classes"] = sum(
            1 for qp in by_q.values() if 0 < np.mean([np.mean(p["miss_r"]) for p in qp]) < 1)
        return out

    overall = auc_block(pairs)
    for name, key in [("a_unknown", "unk"), ("b_empty", "empty"), ("c_hedge", "hedge"), ("d_richness_cv", "rich_miss")]:
        overall[name + "_ci95_by_search"] = boot_auc(pairs, key)
    overall["a_unknown_per_repeat"] = [r3(auc([p["miss_r"][k] for p in pairs], [p["unk"] for p in pairs])) for k in range(3)]
    overall["d_richness_per_repeat"] = [r3(auc([p["miss_r"][k] for p in pairs], rich_r[k])) for k in range(3)]
    overall["d_single_features"] = {nm: r3(np.mean([auc([p["miss_r"][k] for p in pairs], [p["f_" + nm] for p in pairs])
                                                    for k in range(3)])) for nm in FEAT_NAMES}
    vec = [p for p in pairs if p["has_vec"]]
    overall["d_richness_cv_vector_items_only"] = r3(np.mean([auc([p["miss_r"][k] for p in vec], [p["rich_miss_r"][k] for p in vec]) for k in range(3)]))
    R["overall"] = overall
    # grade-2 only
    R["overall_grade2"] = auc_block([p for p in pairs if p["grade"] == 2])
    # enriched only (friends' items excluded)
    R["overall_enriched_only"] = auc_block([p for p in pairs if p["enriched"]])

    # label provenance: answers present before any AI judging (evalset.pre_r1) vs added by judged pools.
    # Pool-added answers came from runs' top 10, so they are found by construction; check the flags hold without them.
    orig = {}
    for ln in open(os.path.join(DATA, "evals", "labels", "evalset.pre_r1.jsonl")):
        q = json.loads(ln)
        orig[q["id"]] = {c for c, g in q["relevant"].items() if g > 0}
    for p in pairs:
        p["orig_label"] = p["c"] in orig.get(p["q"], set())
    R["overall_original_labels_only"] = auc_block([p for p in pairs if p["orig_label"]])
    R["overall_pool_added_labels_only"] = auc_block([p for p in pairs if not p["orig_label"]])

    # per kind (a pair belongs to every mapped kind of its search)
    by_kind = collections.defaultdict(list)
    for p in pairs:
        for k in p["kinds"]:
            by_kind[k].append(p)
    R["per_kind"] = {k: auc_block(v) for k, v in sorted(by_kind.items()) if k in KIND_FACETS}
    small = {"place", "vibe", "people", "said_shown", "audio", "task"}
    R["group_media_facet_kinds"] = auc_block([p for p in pairs if set(p["kinds"]) & small])
    R["group_topic_name"] = auc_block([p for p in pairs if set(p["kinds"]) & {"topic", "name"}])

    # per facet: for pairs whose search needs facet f, AUC of that facet's own flags
    per_facet = {}
    for f in ALL_FACETS:
        ps = [p for p in pairs if f in p["facets"]]
        if not ps:
            continue
        d = {"n_searches": len({p["q"] for p in ps}), "n_pairs": len(ps)}
        for j, nm in enumerate(["unknown", "empty", "hedge"]):
            per = [auc([p["miss_r"][k] for p in ps], [p["state"][f][j] for p in ps]) for k in range(3)]
            per = [x for x in per if x is not None]
            d[nm + "_auc"] = r3(np.mean(per)) if per else None
            d[nm + "_rate"] = r3(np.mean([p["state"][f][j] for p in ps]))
            fl = [p for p in ps if p["state"][f][j]]
            nf = [p for p in ps if not p["state"][f][j]]
            d[nm + "_miss_rate_if_flag"] = r3(np.mean([np.mean(p["miss_r"]) for p in fl])) if fl else None
            d[nm + "_miss_rate_if_not"] = r3(np.mean([np.mean(p["miss_r"]) for p in nf])) if nf else None
        per_facet[f] = d
    R["per_facet"] = per_facet

    # ---- step 3: flag accuracy against the evaluator's MU reading
    R["muse"] = muse_accuracy(enr)

    # ---- step 4: where misses sit
    def bucket(p):
        rs = [r for r in p["ranks"]]
        rs = sorted(1e9 if r is None else r for r in rs)
        med = rs[1]
        if med < 200:
            return "top200"
        if med < 1000:
            return "201_1000"
        return "beyond_1000_or_unranked"

    misses = [p for p in pairs if p["miss"]]
    bk = collections.Counter(bucket(p) for p in misses)
    R["miss_ranks"] = {
        "n_missed_pairs_majority": len(misses),
        "share": {b: r3(bk[b] / len(misses)) for b in ("top200", "201_1000", "beyond_1000_or_unranked")},
        "count": dict(bk),
        "unranked_in_all_3_repeats": sum(1 for p in misses if all(r is None for r in p["ranks"])),
        "note": "runs are stored 1000 deep, so 'beyond' = not in the stored top 1000 (incl. never retrieved)",
        "per_kind_group": {},
        "by_enriched": {},
    }
    for gname, sel in [("topic_name", lambda p: set(p["kinds"]) & {"topic", "name"}),
                       ("more_like_this", lambda p: "more_like_this" in p["kinds"]),
                       ("media_facet_kinds", lambda p: set(p["kinds"]) & small)]:
        ms = [p for p in misses if sel(p)]
        c = collections.Counter(bucket(p) for p in ms)
        R["miss_ranks"]["per_kind_group"][gname] = {"n_searches": len({p["q"] for p in ms}), "n_missed": len(ms),
                                                    **{b: r3(c[b] / len(ms)) if ms else None
                                                       for b in ("top200", "201_1000", "beyond_1000_or_unranked")}}
    for gname, sel in [("enriched", lambda p: p["enriched"]), ("not_enriched", lambda p: not p["enriched"]),
                       ("no_caption_vector", lambda p: not p["has_vec"])]:
        ms = [p for p in misses if sel(p)]
        c = collections.Counter(bucket(p) for p in ms)
        R["miss_ranks"]["by_enriched"][gname] = {"n_missed": len(ms), **{b: r3(c[b] / len(ms)) if ms else None
                                                 for b in ("top200", "201_1000", "beyond_1000_or_unranked")}}
    for p in pairs:
        p["bucket"] = bucket(p) if p["miss"] else None

    # ---- step 5: media gate
    R["gate"] = gate_design(pairs, enr, items, weight, runs, L, rich_corpus(items, pairs, enr))

    with open(os.path.join(WORK, "pairs.jsonl"), "w") as f:
        for p in pairs:
            f.write(json.dumps({k: v for k, v in p.items()}) + "\n")
    json.dump(sanitize(R), open(OUT_JSON, "w"), indent=1)
    print(json.dumps(R, indent=1))


def sanitize(obj):
    """Aggregate-only output: groups of < 3 searches keep AUCs but lose miss rates; < 20 pairs keep only n."""
    if isinstance(obj, dict):
        ns, npairs = obj.get("n_searches"), obj.get("n_pairs")
        out = {}
        for k, v in obj.items():
            if ns is not None and npairs is not None and npairs < 20 and k not in ("n_searches", "n_pairs"):
                continue
            if ns is not None and ns < 3 and "miss_rate" in k:
                continue
            out[k] = sanitize(v)
        if ns is not None and npairs is not None and npairs < 20:
            out["suppressed"] = "fewer than 20 pairs"
        return out
    if isinstance(obj, list):
        return [sanitize(x) for x in obj]
    return obj


# ---------------------------------------------------------------- step 3
def muse_accuracy(enr):
    """Per facet, our `unknown` flag against the evaluator's MU reading (refcmp/judged.jsonl)."""
    from muse import load_records
    from reference_compare import has_mu, mu_core, mu_regex

    samp = [json.loads(l) for l in open(os.path.join(REFCMP, "sample.jsonl"))]
    extra = [json.loads(l) for l in open(os.path.join(REFCMP, "thin_extra.jsonl"))]
    judged = {j["i"]: j for j in map(json.loads, open(os.path.join(REFCMP, "judged.jsonl")))}
    rows = [s for s in samp + extra if s["i"] in judged]
    fac = {"kind": "kind", "topic": "topics", "shown": "shown", "said": "said", "audio": "audio", "place": "place",
           "people": "people", "vibe": "vibe"}

    def table(rows, mu_states, conflict=lambda r, f: False):
        out = {"n_items": len(rows)}
        for mf, of in fac.items():
            cells = collections.Counter()
            gap = gap_flag = 0
            for r in rows:
                e = enr.get(r["code"])
                unk, empty, hedge = facet_state(e, of)
                ms = mu_states(r, mf)
                cells[(("unk" if unk else "known"), ("mu" if ms else "nomu"))] += 1
                if ms and (empty or conflict(r, mf)):
                    gap += 1
                    gap_flag += unk
            n_mu = cells[("unk", "mu")] + cells[("known", "mu")]
            n_known = cells[("known", "mu")] + cells[("known", "nomu")]
            n_unk = cells[("unk", "mu")] + cells[("unk", "nomu")]
            known_agree = sum(1 for r in rows if not facet_state(enr.get(r["code"]), of)[0] and mu_states(r, mf)
                              and not conflict(r, mf))
            out[mf] = {
                "mu_states": r3(n_mu / len(rows)),
                "flag_rate_unknown": r3(n_unk / len(rows)),
                "recall_flag_given_mu_states": r3(cells[("unk", "mu")] / n_mu) if n_mu else None,
                "recall_flag_given_mu_states_and_ours_empty_or_conflict": r3(gap_flag / gap) if gap else None,
                "n_gap": gap,
                "precision_known_mu_agrees": r3(known_agree / n_known) if n_known else None,
                "n_known": n_known,
                "unknown_but_mu_silent": r3(cells[("unk", "nomu")] / n_unk) if n_unk else None,
                "cells": {"unk&mu": cells[("unk", "mu")], "unk&nomu": cells[("unk", "nomu")],
                          "known&mu": cells[("known", "mu")], "known&nomu": cells[("known", "nomu")]},
            }
        return out

    read_states = lambda r, f: f in judged[r["i"]]["mu_cov"]  # noqa: E731
    read_conf = lambda r, f: f in judged[r["i"]].get("conflict", [])  # noqa: E731
    res = {"read_all_126": table(rows, read_states, read_conf),
           "read_sample_112": table([r for r in rows if r["i"] < 1000], read_states, read_conf)}
    # regex extension over the whole MU intersection (cross-check only; regex agrees with reading 75-95%)
    recs = load_records()
    inter = [c for c in enr if c in recs and has_mu(recs[c]["mu"]) and mu_core(recs[c]["mu"])]
    rx = {c: mu_regex(mu_core(recs[c]["mu"]), recs[c]["music"]) for c in inter}
    res["regex_intersection"] = table([{"code": c} for c in inter], lambda r, f: rx[r["code"]][f])
    return res


# ---------------------------------------------------------------- step 5
AUDIO_KINDS = {"music_dance", "meme_joke", "skit"}  # music, dance, trend formats
SAID_KINDS = {"tutorial", "tips", "review", "news_info", "motivation", "vlog", "recipe"}  # talking heads / how-to
RUNG_FACETS = {
    "image": {"shown", "vibe", "said", "place"},  # thumbnail / 1 frame: shown, on-screen text, vibe, landmarks
    "audio": {"said", "audio"},  # speech, song
    "video": set(ALL_FACETS),  # everything
}


def prices():
    P = json.load(open(PRICES))["models"]["gemini-3.1-flash-lite"]
    return P


def rung_cost_per_1k(text_in, out_tok=250, secs=30):
    """Flash-Lite describe pass, USD per 1,000 items, standard and batch (half), at ai_prices.json prices.
    Media tokens (Gemini 3 table, research/mlt-multimodal-audio-media.md): image low res 280; audio 25/s;
    video 70/frame at 1 fps (+ its audio track)."""
    P = prices()
    t, m, a, o = P["input_per_m"] / 1e6, P["media_input_per_m"] / 1e6, P["audio_input_per_m"] / 1e6, P["output_per_m"] / 1e6
    base = text_in * t + out_tok * o
    c = {"image": base + 280 * m, "audio": base + 25 * secs * a, "video": base + 70 * secs * m + 25 * secs * a}
    return {k: {"standard": round(v * 1000, 3), "batch": round(v * 500, 3)} for k, v in c.items()}


def rich_corpus(items, pairs, enr):
    """Round-0 richness score for every enrichable item: logistic fit on all dev pairs (in-sample, so optimistic
    for the richness baseline), applied corpus-wide. Returns {code: P(found)}."""
    codes = sorted(c for c in items if c in enr)
    F, _ = richness_features(items, codes)
    pc = sorted({p["c"] for p in pairs})
    Fp, _ = richness_features(items, pc)
    idx = {c: i for i, c in enumerate(pc)}
    Xp = np.array([Fp[idx[p["c"]]] for p in pairs])
    mu, sd = Xp.mean(0), Xp.std(0) + 1e-9
    y = np.array([1 - p["miss"] for p in pairs])
    clf = LogisticRegression(max_iter=2000, class_weight="balanced").fit((Xp - mu) / sd, y)
    sc = clf.predict_proba((F - mu) / sd)[:, 1]
    return dict(zip(codes, sc.tolist()))


def gate_design(pairs, enr, items, weight, runs, L, rich):
    universe = [c for c in items if c in enr]  # enrichable (non-friend) items
    N = len(universe)
    # search demand per facet: share of all searches (queries.jsonl, method side, 22) needing the facet
    qs = [json.loads(l) for l in open(os.path.join(DATA, "evals", "queries.jsonl"))]
    dem = collections.Counter()
    for q in qs:
        for f in search_facets(q["kinds"]):
            dem[f] += 1
    demand = {f: round(dem[f] / len(qs), 3) for f in ALL_FACETS}

    def st(c, f):
        return facet_state(enr.get(c), f)

    def gap(c, f):
        u, e, _ = st(c, f)
        return u or e

    def is_post(c):
        return items[c]["platform_data"]["media_kind"] == "post"

    W = lambda c: weight.get(c, 0.0)  # noqa: E731
    K = lambda c: (enr[c].get("kind") if c in enr else None)  # noqa: E731
    thin = lambda c: info_class(items[c]) != "ok"  # noqa: E731

    rules = {
        # rung: {rule_name: predicate}
        "image": {
            "gap(shown|vibe) & w>=0.8": lambda c: (gap(c, "shown") or gap(c, "vibe")) and W(c) >= 0.8,
            "gap(shown|vibe) & (w>=0.8 | thin)": lambda c: (gap(c, "shown") or gap(c, "vibe")) and (W(c) >= 0.8 or thin(c)),
            "gap(shown|vibe|place) & w>=0.6": lambda c: (gap(c, "shown") or gap(c, "vibe") or gap(c, "place")) and W(c) >= 0.6,
            "gap(shown|vibe|place)": lambda c: gap(c, "shown") or gap(c, "vibe") or gap(c, "place"),
        },
        "audio": {
            "reel & ((audio gap & audio-kind) | (said gap & said-kind)) & w>=0.8":
                lambda c: not is_post(c) and ((gap(c, "audio") and K(c) in AUDIO_KINDS) or (gap(c, "said") and K(c) in SAID_KINDS)) and W(c) >= 0.8,
            "reel & ((audio gap & audio-kind) | (said gap & said-kind))":
                lambda c: not is_post(c) and ((gap(c, "audio") and K(c) in AUDIO_KINDS) or (gap(c, "said") and K(c) in SAID_KINDS)),
            "reel & (audio|said gap) & w>=0.8": lambda c: not is_post(c) and (gap(c, "audio") or gap(c, "said")) and W(c) >= 0.8,
        },
        "video": {
            "reel & w>=0.8 & thin": lambda c: not is_post(c) and W(c) >= 0.8 and thin(c),
            "reel & w>=0.8 & >=4 of 7 media/text facets gap": lambda c: not is_post(c) and W(c) >= 0.8 and sum(
                gap(c, f) for f in ["kind", "shown", "said", "place", "people", "vibe", "use"]) >= 4,
            "reel & w>=0.8": lambda c: not is_post(c) and W(c) >= 0.8,
        },
    }
    text_in = statistics.mean(r["in_tokens"] for r in enr.values() if r.get("in_tokens"))
    cost = rung_cost_per_1k(text_in)
    cost_note = (f"Flash-Lite describe at ai_prices.json ({json.load(open(PRICES))['verified_on']}); text input "
                 f"{text_in:.0f} tok (te-v1c mean, prompt + caption), 250 output tok, 30 s reels assumed (no durations "
                 "in the export); image low res 280 tok; audio 25 tok/s; video 70 tok/frame at 1 fps + audio.")
    misses = [p for p in pairs if p["miss"]]
    n_reel = sum(1 for c in universe if not is_post(c))

    def covered(sel, rung, ps):
        """share of missed pairs whose answer is selected; and selected + the rung fills a facet the search needs."""
        if not ps:
            return None, None
        a = sum(1 for p in ps if p["c"] in sel)
        b = sum(1 for p in ps if p["c"] in sel and (set(p["facets"]) & RUNG_FACETS[rung]))
        return r3(a / len(ps)), r3(b / len(ps))

    out = {"universe_enrichable_items": N, "reels": n_reel, "posts": N - n_reel, "search_demand_by_facet": demand,
           "cost_per_1k_items_usd": cost, "cost_note": cost_note, "rungs": {}}
    for rung, rs in rules.items():
        out["rungs"][rung] = {}
        for name, pred in rs.items():
            sel = {c for c in universe if pred(c)}
            cov_any, cov_fac = covered(sel, rung, misses)
            share = len(sel) / N
            out["rungs"][rung][name] = {
                "corpus_share": r3(share), "n_items": len(sel),
                "usd_per_1k_corpus_items_batch": round(share * cost[rung]["batch"], 3),
                "usd_per_1k_corpus_items_standard": round(share * cost[rung]["standard"], 3),
                "misses_covered_item": cov_any, "misses_covered_item_and_facet": cov_fac,
                "misses_covered_by_bucket_item_and_facet": {
                    b: covered(sel, rung, [p for p in misses if p["bucket"] == b])[1]
                    for b in ("top200", "201_1000", "beyond_1000_or_unranked")},
            }
        # everything
        sel = set(universe) if rung == "image" else {c for c in universe if not is_post(c)}
        cov_any, cov_fac = covered(sel, rung, misses)
        out["rungs"][rung]["EVERYTHING (" + ("all items" if rung == "image" else "all reels") + ")"] = {
            "corpus_share": r3(len(sel) / N), "n_items": len(sel),
            "usd_per_1k_corpus_items_batch": round(len(sel) / N * cost[rung]["batch"], 3),
            "usd_per_1k_corpus_items_standard": round(len(sel) / N * cost[rung]["standard"], 3),
            "misses_covered_item": cov_any, "misses_covered_item_and_facet": cov_fac}
    # on-demand only: a weak search enriches its own top-N candidates (synchronous, standard price)
    od = {}
    for Nn in (50, 200, 1000):
        reach = [p for p in misses if p["ranks"] and sorted(1e9 if r is None else r for r in p["ranks"])[1] < Nn]
        union = set()
        for r in runs[:1]:
            for q in L:
                union |= set(r["queries"].get(q, [])[:Nn])
        od[f"top{Nn}"] = {
            "misses_reachable": r3(len(reach) / len(misses)),
            "misses_reachable_and_rung_fills_facet": {rung: r3(sum(1 for p in reach if set(p["facets"]) & RUNG_FACETS[rung]) / len(misses))
                                                      for rung in RUNG_FACETS},
            "usd_per_1k_searches_standard": {rung: round(Nn * cost[rung]["standard"], 2) for rung in RUNG_FACETS},
            "unique_items_16_dev_searches": len(union), "share_of_corpus_16_dev_searches": r3(len(union) / N),
            "added_latency_note": "one describe call per candidate; parallel calls of ~1-2 s each",
        }
    out["on_demand_only"] = od
    # interaction weight and kind profile of the missed answers (aggregate)
    out["missed_answers_profile"] = {
        "w>=0.8 (self-share/save/collection)": r3(np.mean([W(p["c"]) >= 0.8 for p in misses])),
        "w==0.6 (friend share)": r3(np.mean([W(p["c"]) == 0.6 for p in misses])),
        "w<=0.3 (like/watch only)": r3(np.mean([W(p["c"]) <= 0.3 for p in misses])),
        "reel": r3(np.mean([not is_post(p["c"]) for p in misses])),
        "thin_caption": r3(np.mean([thin(p["c"]) for p in misses])),
        "kind_audio_kinds": r3(np.mean([K(p["c"]) in AUDIO_KINDS for p in misses])),
        "kind_said_kinds": r3(np.mean([K(p["c"]) in SAID_KINDS for p in misses])),
    }
    out["corpus_profile"] = {
        "w>=0.8": r3(np.mean([W(c) >= 0.8 for c in universe])),
        "w==0.6": r3(np.mean([W(c) == 0.6 for c in universe])),
        "w<=0.3": r3(np.mean([W(c) <= 0.3 for c in universe])),
        "reel": r3(n_reel / N), "thin_caption": r3(np.mean([thin(c) for c in universe])),
        "kind_audio_kinds": r3(np.mean([K(c) in AUDIO_KINDS for c in universe])),
        "kind_said_kinds": r3(np.mean([K(c) in SAID_KINDS for c in universe])),
    }
    # scored gate: score = interaction weight x sum over rung facets of gap x kind relevance x search demand
    def rel(c, f):
        k = K(c)
        if f == "audio":
            return 1.0 if k in AUDIO_KINDS else 0.3
        if f == "said":
            return 1.0 if k in SAID_KINDS else 0.3
        return 1.0

    def gscore(c, rung, use_w=True):
        fs = RUNG_FACETS[rung]
        v = sum(gap(c, f) * rel(c, f) * max(demand[f], 0.02) for f in fs)
        if rung != "image" and is_post(c):
            return -1.0
        return v * (W(c) if use_w else 1.0) + 1e-6 * (W(c) if use_w else 0)

    rng = np.random.default_rng(3)
    jitter = {c: float(x) for c, x in zip(universe, rng.random(len(universe)))}
    curves = {}
    for rung in RUNG_FACETS:
        elig = [c for c in universe if rung == "image" or not is_post(c)]
        orders = {
            "gate (w x gap x kind-relevance x demand)": sorted(elig, key=lambda c: (-gscore(c, rung), jitter[c])),
            "gate without interaction weight": sorted(elig, key=lambda c: (-gscore(c, rung, False), jitter[c])),
            "interaction weight only": sorted(elig, key=lambda c: (-W(c), jitter[c])),
            "caption richness (round 0, lowest first)": sorted(elig, key=lambda c: (rich[c], jitter[c])),
            "random": sorted(elig, key=lambda c: jitter[c]),
        }
        curves[rung] = {}
        for oname, order in orders.items():
            curves[rung][oname] = {}
            for frac in (0.1, 0.25, 0.5):
                n = int(round(frac * N))
                sel = set(order[:n])
                ca, cf = covered(sel, rung, misses)
                curves[rung][oname][f"{int(frac * 100)}%"] = {
                    "usd_per_1k_corpus_items_batch": round(frac * cost[rung]["batch"], 3),
                    "misses_covered_item": ca, "misses_covered_item_and_facet": cf,
                    "found_answers_selected": r3(np.mean([p["c"] in sel for p in pairs if not p["miss"]]))}
    out["scored_gate_curves"] = curves
    out["kind_relevance"] = {"audio": sorted(AUDIO_KINDS), "said": sorted(SAID_KINDS), "other facets": "all kinds",
                             "off-kind weight": 0.3}
    out["found_answers_profile"] = {
        "w>=0.8": r3(np.mean([W(p["c"]) >= 0.8 for p in pairs if not p["miss"]])),
    }
    return out


if __name__ == "__main__":
    main()
