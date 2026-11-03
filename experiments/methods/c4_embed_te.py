"""PROTOTYPE ONLY - round 4.1: build the te-v1c enrichment index files used by c4_lib.EnrichIdx.

  Instagram (Y4.1-TE rows): $DIGESTER_DATA/enrich/te-v1c_ig_<model>.jsonl -> enrich/text_<name>.json (round 1's
      e9_enrich_search.enrich_text, last ok row per item wins) and corpus/emb/emb_<name>/ (text-embedding-3-small,
      512 d, one ai.openai_embed call per 500 texts; ledger + budget).
  YouTube (round 3, reused, no spend): copies data/yt/corpus/emb/emb_te-v1c_allowed_<model>/ to
      corpus/emb/emb_yt_te-v1c_allowed_<model>/ (its texts are read from yt_enrich/ in place).
Logs items processed, items/s and wall time. Prints aggregate numbers only.
"""
import json
import os
import shutil
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import c4_lib as L
import yt_lib as Y
from corpus import DATA, REPO
from e9_enrich_search import enrich_text


def main():
    t0 = time.time()
    rows = {}
    for r in L.jl(os.path.join(DATA, "enrich", f"{L.TE_IG}.jsonl")):
        if r.get("ok"):
            rows[r["code"]] = r
    texts = {c: enrich_text(r) for c, r in sorted(rows.items())}
    json.dump(texts, open(os.path.join(DATA, "enrich", f"text_{L.TE_IG}.json"), "w"))
    codes = list(texts)
    print(f"instagram te rows ok {len(codes)}, mean {np.mean([len(t) for t in texts.values()]):.0f} chars", flush=True)
    V = Y.embed_texts([texts[c] for c in codes], "c4_embed_te_ig", batch=500, workers=4)
    L.save_store(os.path.join(L.EMB, f"emb_{L.TE_IG}"), codes, V)
    src = os.path.join(REPO, "data", "yt", "corpus", "emb", f"emb_{L.TE_YT}")
    dst = os.path.join(L.EMB, f"emb_yt_{L.TE_YT}")
    if not os.path.exists(dst):
        shutil.copytree(src, dst)
    n_yt = len(json.load(open(os.path.join(dst, "ids.json"))))
    el = time.time() - t0
    print(f"embedded {len(codes)} items in {el:.1f} s ({len(codes) / el:.0f} items/s); youtube te store {n_yt} rows")


if __name__ == "__main__":
    main()
