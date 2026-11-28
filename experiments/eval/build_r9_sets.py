"""PROTOTYPE ONLY - EVALUATOR SIDE. Round-9 setup: Derrick's 8 Nov labels and his round-9 search sheet.

Reads (evaluator-only, never by builders):
  $DIGESTER_DATA/evals/labels/derrick_inputs/derrick-labels-2026-11-08.json  (ig_real, calibration, intent_updates)
  $DIGESTER_DATA/evals/labels/derrick_inputs/search-sheet-r9-answers.json   (facet_real source)

Writes (all under $DIGESTER_DATA/evals/, gitignored), after backing up evalset.jsonl / queries.jsonl / split.json
as *.pre_r9.0.*:
  1. intent_updates appended to the two dev searches' `intent` in labels/evalset.jsonl (idempotent).
  2. ig_real: seed labels (Derrick only) in labels/ig_real.jsonl, the same rows in labels/evalset.jsonl (the working
     labels that pooled grades are merged into), texts hidden in labels/ig_real_queries.jsonl, split `ig_real`.
     Grades use the 4-point scale (`grade_scale`): Derrick wrote each search for that post, so the target is 3
     (his sheet's 2 = "the post I had in mind"); mrr2 / s10_2 count grade >= 2, so the known-item slice is unchanged.
  3. facet_real: one search per non-skipped sheet item (first search line; the number of lines is recorded),
     facets = based_on, specificity = want; target grade 3 (exact: the item; like: one good answer, the other top-10
     items are pool-judged). Split by item, stratified by the rarest ticked facet (seed 9), alternating within
     strata: facet_dev (texts method-side in queries.jsonl, ids fdv.., kinds = facets only) and facet_test (texts
     hidden in labels/facet_test_queries.jsonl, ids fts..). Seed labels in labels/facet_real.jsonl, working labels in
     labels/evalset.jsonl.
Prints aggregates only.

usage: python experiments/eval/build_r9_sets.py
"""
import collections
import json
import os
import random
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from corpus import DATA  # noqa: E402

EV = os.path.join(DATA, "evals")
LAB = os.path.join(EV, "labels")
INP = os.path.join(LAB, "derrick_inputs")
SEED = 9
STAMP = "pre_r9.0"
SCALE4 = "0-3 (0 wrong, 1 related, 2 good, 3 exactly meant)"
FACETS = ["creator", "topic", "type", "looks", "sound", "said", "tone", "examples", "when", "other"]


def jl_read(p):
    return [json.loads(line) for line in open(p, encoding="utf-8") if line.strip()]


def jl_write(p, rows):
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def backup():
    for p in [os.path.join(LAB, "evalset.jsonl"), os.path.join(EV, "queries.jsonl"), os.path.join(EV, "split.json")]:
        root, ext = os.path.splitext(p)
        b = f"{root}.{STAMP}{ext}"
        if not os.path.exists(b):
            shutil.copy2(p, b)


def main():
    labels = json.load(open(os.path.join(INP, "derrick-labels-2026-11-08.json")))
    sheet = json.load(open(os.path.join(INP, "search-sheet-r9-answers.json")))
    backup()
    ev_path, q_path, sp_path = os.path.join(LAB, "evalset.jsonl"), os.path.join(EV, "queries.jsonl"), os.path.join(EV, "split.json")
    ev = [r for r in jl_read(ev_path) if not r["id"].startswith(("igr", "fdv", "fts"))]
    byid = {r["id"]: r for r in ev}

    # 1. intent updates
    applied = 0
    for qid, add in labels["intent_updates"].items():
        cur = byid[qid].get("intent") or ""
        if add.strip() not in cur:
            byid[qid]["intent"] = (cur.rstrip() + " " + add.strip()).strip()
            applied += 1
    print(f"intent_updates: {len(labels['intent_updates'])} given, {applied} newly applied")

    # 2. ig_real
    igr = []
    for r in labels["ig_real"]:
        row = dict(r)
        row["relevant"] = {c: 3 for c in r["relevant"]}
        row["grade_scale"] = SCALE4
        row["searched_at"] = None
        row["note"] = "; ".join(x for x in [r.get("note", ""), "target 3 = the post Derrick wrote this search for "
                                            "(his sheet's 2); other items unjudged until pooled"] if x)
        igr.append(row)
    jl_write(os.path.join(LAB, "ig_real.jsonl"), igr)
    jl_write(os.path.join(LAB, "ig_real_queries.jsonl"),
             [{"id": r["id"], "query": r["query"], "kinds": r["kinds"], "examples": [], "filters": {}} for r in igr])
    print("ig_real", len(igr), dict(collections.Counter(r["search_kind"] for r in igr)),
          "targets", sum(len(r["relevant"]) for r in igr),
          "caption revealed", sum(1 for r in igr if "revealed" in r["note"]))

    # 3. facet_real
    kept = [x for x in sheet["items"] if not x["skip"] and x["searches"]]
    freq = collections.Counter(f for x in kept for f in x["based_on"])

    def stratum(x):
        return min(x["based_on"], key=lambda f: (freq[f], FACETS.index(f))) if x["based_on"] else "none"

    strata = collections.defaultdict(list)
    for x in kept:
        strata[stratum(x)].append(x)
    rng = random.Random(SEED)
    dev, test, flip = [], [], 0
    for key in sorted(strata, key=lambda k: (freq.get(k, 0), k)):
        g = sorted(strata[key], key=lambda x: x["code"])
        rng.shuffle(g)
        g.sort(key=lambda x: x["platform"])  # stable: platforms alternate within a stratum
        for i, x in enumerate(g):
            (dev if (i + flip) % 2 == 0 else test).append(x)
        if len(g) % 2:
            flip ^= 1
    intents = {"exact": "Find this specific item I remember.",
               "like": "Anything like the item I had in mind; that item is one good answer among others."}
    src = "facet_real: Derrick's searches for sampled library items, round-9 search sheet (9 Nov 2026)"

    def rows(part, prefix):
        out_q, out_l = [], []
        for n, x in enumerate(sorted(part, key=lambda x: x["code"])):
            qid = f"{prefix}{n:02d}"
            kinds = list(x["based_on"])
            q = {"id": qid, "query": x["searches"][0], "kinds": kinds, "examples": [], "filters": {}}
            lab = {**q, "scope": "ig" if x["platform"] == "IG" else "yt", "relevant": {x["code"]: 3},
                   "judged_nonrelevant": [], "intent": intents[x["want"]], "specificity": x["want"],
                   "facets": kinds, "grade_scale": SCALE4, "n_search_lines": len(x["searches"]),
                   "caption_revealed": bool(x["caption_revealed"]), "sample_stratum": x["stratum"],
                   "split_stratum": stratum(x), "searched_at": None, "source": src,
                   "note": "target 3; " + ("known item" if x["want"] == "exact" else
                                           "one good answer, other top-10 items pool-judged")}
            out_q.append(q)
            out_l.append(lab)
        return out_q, out_l

    dq, dl = rows(dev, "fdv")
    tq, tl = rows(test, "fts")
    jl_write(os.path.join(LAB, "facet_real.jsonl"), dl + tl)
    jl_write(os.path.join(LAB, "facet_test_queries.jsonl"), tq)
    ev += igr + dl + tl
    jl_write(ev_path, ev)
    qs = [r for r in jl_read(q_path) if not r["id"].startswith(("igr", "fdv", "fts"))] + dq
    jl_write(q_path, qs)
    sp = json.load(open(sp_path))
    sp["ig_real"] = sorted(r["id"] for r in igr)
    sp["facet_dev"] = sorted(r["id"] for r in dl)
    sp["facet_test"] = sorted(r["id"] for r in tl)
    add = (" ig_real = Derrick's 31 real Instagram searches for his own posts (8 Nov; kinds known_item / topic / meta; "
           "4-point grades, target 3); queries hidden in labels/ig_real_queries.jsonl. facet_dev / facet_test = "
           "Derrick's round-9 search sheet (one search per item, kinds = the facets he ticked; 4-point grades, target 3), "
           "split by item stratified by facet (seed 9); facet_test queries hidden in labels/facet_test_queries.jsonl.")
    if "ig_real =" not in sp["_note"]:
        sp["_note"] += add
    json.dump(sp, open(sp_path, "w"), indent=1)

    lines2 = sum(1 for x in kept if len(x["searches"]) > 1)
    print(f"facet_real {len(kept)} searches (skipped {len(sheet['items']) - len(kept)}; two lines: {lines2})")
    for name, part in (("facet_dev", dev), ("facet_test", test)):
        print(name, len(part), "platform", dict(collections.Counter(x["platform"] for x in part)),
              "want", dict(collections.Counter(x["want"] for x in part)),
              "facets", dict(collections.Counter(f for x in part for f in x["based_on"])),
              "unticked", sum(1 for x in part if not x["based_on"]))


if __name__ == "__main__":
    main()
