"""PROTOTYPE ONLY. Build the combined Instagram + YouTube data root for round 4.

    python experiments/combined/build_root.py --ig <ig data root> --yt data/yt --out data/all

Merges items, interactions, OpenAI text-embedding-3-small 512d vectors (both roots used that model),
queries (Instagram ids get an `ig_` prefix), labels (each search gets `scope`: ig | yt) and the split.
Reuses YouTube enrichment outputs by symlink. Nothing here calls a paid API.
"""

import argparse
import json
import os

import numpy as np


def jl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def wl(p, rows):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ig", required=True)
    ap.add_argument("--yt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ig-emb", default="openai3s_512")
    ap.add_argument("--yt-emb", default="oai512_allowed")
    a = ap.parse_args()
    out = a.out

    # items + interactions
    ig_items, yt_items = jl(f"{a.ig}/corpus/items.jsonl"), jl(f"{a.yt}/corpus/items.jsonl")
    ids = {i["id"] for i in ig_items}
    codes = {i["dedup_key"].split(":", 1)[1] for i in ig_items}
    clash_id = sum(i["id"] in ids for i in yt_items)
    clash_code = sum(i["dedup_key"].split(":", 1)[1] in codes for i in yt_items)
    assert clash_id == 0 and clash_code == 0, (clash_id, clash_code)
    wl(f"{out}/corpus/items.jsonl", ig_items + yt_items)
    wl(f"{out}/corpus/interactions.jsonl",
       jl(f"{a.ig}/corpus/interactions.jsonl") + jl(f"{a.yt}/corpus/interactions.jsonl"))

    # vectors (same model, 512d)
    vi, vy = [], []
    for root, emb, acc in ((a.ig, a.ig_emb, vi), (a.yt, a.yt_emb, vy)):
        d = f"{root}/corpus/emb/{emb}"
        acc.append(json.load(open(f"{d}/ids.json")))
        acc.append(np.load(f"{d}/emb.npy").astype(np.float16))
    d = f"{out}/corpus/emb/oai512"
    os.makedirs(d, exist_ok=True)
    json.dump(vi[0] + vy[0], open(f"{d}/ids.json", "w"))
    np.save(f"{d}/emb.npy", np.vstack([vi[1], vy[1]]))

    # queries, labels, split
    def ig_q(q):
        q = dict(q)
        q["id"] = "ig_" + q["id"]
        return q

    ig_qs = [ig_q(q) for q in jl(f"{a.ig}/evals/queries.jsonl")]
    yt_qs = jl(f"{a.yt}/evals/queries.jsonl")
    wl(f"{out}/evals/queries.jsonl", ig_qs + yt_qs)
    ig_lab = [dict(ig_q(r), scope="ig") for r in jl(f"{a.ig}/evals/labels/evalset.jsonl")]
    yt_lab = [dict(r, scope="yt") for r in jl(f"{a.yt}/evals/labels/evalset.jsonl")]
    wl(f"{out}/evals/labels/evalset.jsonl", ig_lab + yt_lab)
    ig_split = json.load(open(f"{a.ig}/evals/split.json"))
    yt_split = json.load(open(f"{a.yt}/evals/split.json"))
    split = {
        "_note": ("dev = all Instagram searches (their test split is used up: 3 of 3) + YouTube dev. "
                  "yt_holdout = YouTube test (2 scorings left). test = Derrick's fresh searches, written "
                  "before any round-4 result; scored at most 3 times, by the evaluator only."),
        "dev": ["ig_" + x for x in ig_split["dev"] + ig_split["test"]] + yt_split["dev"],
        "yt_holdout": yt_split["test"],
        "test": [],
    }
    json.dump(split, open(f"{out}/evals/split.json", "w"), indent=1)

    # reuse YouTube enrichment outputs (read-only)
    for sub in ("enrich", "video", "ref"):
        src = os.path.abspath(f"{a.yt}/{sub}")
        dst = f"{out}/yt_{sub}"
        if os.path.isdir(src) and not os.path.exists(dst):
            os.symlink(src, dst)
    print(json.dumps({"items": len(ig_items) + len(yt_items), "ig": len(ig_items), "yt": len(yt_items),
                      "vectors": len(vi[0]) + len(vy[0]), "queries": len(ig_qs) + len(yt_qs),
                      "dev": len(split["dev"]), "yt_holdout": len(split["yt_holdout"])}))


if __name__ == "__main__":
    main()
