"""PROTOTYPE ONLY - round 6 G4: re-embed every item view with text-embedding-3-large at 1,024 d (LOG.md Y6-G4).

  check  re-embeds 200 random items' views with text-embedding-3-small @ 512 d and compares them with the stored
         corpus/emb/oai512 vectors (must be cosine >= 0.995), so the 3-large vectors are of the same texts.
  build  embeds the same 121,169 views (c4_lib.view_text, cut at 6,000 chars), in oai512's id order, into
         corpus/emb/oai3l_1024/ (ids.json + emb.npy, float16). Resumable: 5,000-item chunks in chunks/.
         Synchronous ai.openai_embed calls of 500 texts (ledger + budget); no batch price is published for this
         model, so the Batch API is not used. Logs items processed, items/s, wall time and cost.
Prints aggregates only.

usage: python experiments/methods/c6_embed.py check | build [--workers 2]
"""
import argparse
import json
import os
import sys
import time

import numpy as np
from sklearn.preprocessing import normalize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import ai  # noqa: E402
import c4_lib as L  # noqa: E402
import c6_lib as G  # noqa: E402
from corpus import DATA  # noqa: E402

OUT = os.path.join(L.EMB, G.STORE_3L)
CHUNK = 5000


def views():
    items = {it["id"]: it for it in L.jl(os.path.join(DATA, "corpus", "items.jsonl"))}
    ids = json.load(open(os.path.join(L.EMB, "oai512", "ids.json")))
    return ids, [L.view_text(items[i])[:6000] for i in ids]


def spent_purpose(purpose):
    return sum(r["cost_usd"] for r in L.ledger() if r.get("purpose") == purpose)


def check():
    ids, texts = views()
    rng = np.random.default_rng(6)
    pick = sorted(rng.choice(len(ids), 200, replace=False).tolist())
    old = normalize(np.load(os.path.join(L.EMB, "oai512", "emb.npy"))[pick].astype(np.float32))
    new = normalize(np.array(ai.openai_embed([texts[k] or " " for k in pick], model="text-embedding-3-small",
                                             dimensions=512, purpose="c6_view_check"), dtype=np.float32))
    cos = (old * new).sum(1)
    print(json.dumps({"n": len(pick), "cos_min": round(float(cos.min()), 5), "cos_p01": round(float(np.percentile(cos, 1)), 5),
                      "cos_mean": round(float(cos.mean()), 5), "below_0.995": int((cos < 0.995).sum()),
                      "n_instagram_view": sum(k < 20202 for k in pick)}))
    return float(cos.min())


def build(workers):
    ids, texts = views()
    os.makedirs(os.path.join(OUT, "chunks"), exist_ok=True)
    t0 = time.time()
    cost0 = spent_purpose("c6_embed_items_3l")
    done = 0
    for c in range(0, len(texts), CHUNK):
        p = os.path.join(OUT, "chunks", f"chunk_{c // CHUNK:03d}.npy")
        if os.path.exists(p):
            done += min(CHUNK, len(texts) - c)
            continue
        t1 = time.time()
        V = G.embed_3l(texts[c:c + CHUNK], "c6_embed_items_3l", batch=500, workers=workers)
        np.save(p, V.astype(np.float16))
        done += len(V)
        el = time.time() - t0
        print(f"{done}/{len(texts)} items, chunk {time.time() - t1:.1f} s, {done / max(el, 1e-9):.0f} items/s overall, "
              f"cost so far ${spent_purpose('c6_embed_items_3l'):.4f}", flush=True)
    V = np.concatenate([np.load(os.path.join(OUT, "chunks", f"chunk_{c // CHUNK:03d}.npy"))
                        for c in range(0, len(texts), CHUNK)])
    assert V.shape == (len(ids), G.EMB3L_DIM), V.shape
    np.save(os.path.join(OUT, "emb.npy"), V.astype(np.float16))
    json.dump(ids, open(os.path.join(OUT, "ids.json"), "w"))
    rows = [r for r in L.ledger() if r.get("purpose") == "c6_embed_items_3l"]
    summary = {"items": len(ids), "dim": G.EMB3L_DIM, "model": G.EMB3L_MODEL, "calls": len(rows),
               "tokens": sum(r["in_tokens"] for r in rows), "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
               "cost_this_invocation_usd": round(spent_purpose("c6_embed_items_3l") - cost0, 4),
               "wall_this_invocation_s": round(time.time() - t0, 1),
               "sum_call_seconds": round(sum(r["seconds"] for r in rows), 1),
               "store_mb": round(os.path.getsize(os.path.join(OUT, "emb.npy")) / 1e6, 1)}
    json.dump(summary, open(os.path.join(OUT, "build_summary.json"), "w"), indent=1)
    print(json.dumps(summary), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check", "build"])
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    if a.cmd == "check":
        check()
    else:
        build(a.workers)


if __name__ == "__main__":
    main()
