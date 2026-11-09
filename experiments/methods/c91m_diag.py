"""PROTOTYPE ONLY - round 9.1 Track 2 label-free diagnostics of runs/r9.1/m_r{k} and m2_r{k} vs runs/r9.1/q8ref_r{k}.

No labels, no eval_work/. Facet groups come from the Phase-A tagger (evals/facet_tags.json, method side) plus, for
facet_dev, the user's ticks carried in queries.jsonl `kinds`. Prints and writes aggregates only (counts / means per
split and facet group; never query text, ids or item codes).

usage: python experiments/methods/c91m_diag.py [--out FILE]
"""
import argparse
import collections
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
from corpus import DATA, load_queries  # noqa: E402

RUNS = os.path.join(DATA, "runs", "r9.1")
MEDIA = {"looks", "sound", "said"}
SPLITS = ["dev", "known_dev", "ig_known_dev", "facet_dev"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(DATA, "tmp", "r9.1_media_checks", "diag.json"))
    a = ap.parse_args()
    t0 = time.time()
    tags = json.load(open(os.path.join(DATA, "evals", "facet_tags.json")))["tags"]
    split_of, kinds = {}, {}
    for sp in SPLITS:
        for q in load_queries(sp):
            split_of[q["id"]] = sp
            kinds[q["id"]] = set(q.get("kinds") or []) if sp == "facet_dev" else set()
    desc = set(json.load(open(os.path.join(DATA, "media_pilot", "emb_md-v1", "ids.json"))))
    res = {}
    n = 0
    for arm, rep in [(a, r) for a in ("m", "m2") for r in (1, 2, 3)]:
        if not os.path.exists(os.path.join(RUNS, f"{arm}_r{rep}.json")):
            continue
        m = json.load(open(os.path.join(RUNS, f"{arm}_r{rep}.json")))
        b = json.load(open(os.path.join(RUNS, f"q8ref_r{rep}.json")))
        per = m["meta"]["per_search"]
        grp = collections.defaultdict(lambda: collections.defaultdict(list))
        for k, sp in split_of.items():
            if k not in per:  # more-like-this
                continue
            n += 1
            f = set((tags.get(k) or {}).get("facets") or []) | kinds[k]
            g = "media-tagged" if f & MEDIA else ("tagged, other" if k in tags or sp == "facet_dev" else "untagged")
            for key in ((sp, "all"), (sp, g)):
                d = grp[key]
                x, y = m["queries"][k], b["queries"][k]
                d["n"].append(1)
                d["top10_changed"].append(x[:10] != y[:10])
                d["top10_set_changed"].append(set(x[:10]) != set(y[:10]))
                d["desc_top10_m"].append(sum(c in desc for c in x[:10]))
                d["desc_top10_b"].append(sum(c in desc for c in y[:10]))
                d["desc_top1_m"].append(x[0] in desc if x else False)
                d["desc_top1_b"].append(y[0] in desc if y else False)
        res[f"{arm}_r{rep}"] = {f"{sp}|{g}": {"n": len(d["n"]),
                                        "top10_changed": int(sum(d["top10_changed"])),
                                        "top10_set_changed": int(sum(d["top10_set_changed"])),
                                        "described_in_top10_mean_m": round(float(np.mean(d["desc_top10_m"])), 3),
                                        "described_in_top10_mean_q8": round(float(np.mean(d["desc_top10_b"])), 3),
                                        "described_at_rank1_m": int(sum(d["desc_top1_m"])),
                                        "described_at_rank1_q8": int(sum(d["desc_top1_b"]))}
                          for (sp, g), d in sorted(grp.items())}
    wall = time.time() - t0
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({"note": "label-free aggregates; no ids or text", "groups": res, "wall_s": round(wall, 1)},
              open(a.out, "w"), indent=1)
    for arm in res:
        if arm.endswith("_r1"):
            for key, v in res[arm].items():
                print(f"{arm} {key}: {v}")
    print(f"diag: {n} search-repeats in {wall:.1f} s ({n / max(wall, 1e-9):.0f} items/s) -> {a.out}", flush=True)


if __name__ == "__main__":
    main()
